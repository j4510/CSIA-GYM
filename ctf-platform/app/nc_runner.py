"""
Netcat / Reverse Engineering Challenge Runner — per-user subprocess instances.

Each (challenge_id, user_id) pair gets its own socat listener on a unique port.
Instances expire after 15 minutes. Users may extend while ≤ 30 minutes remain,
up to a hard cap of 60 minutes total from the original launch time.

A background reaper thread checks every 30 seconds and kills expired instances.

Port range: 11000–11999 (must be exposed in docker-compose.yml).
"""

import os
import secrets
import hashlib
import shlex
import stat
import glob
import socket
import shutil
import tarfile
import subprocess
import threading
import time

PORT_RANGE_START = 11000
PORT_RANGE_END   = 11099

INITIAL_TTL  = 15 * 60
HARD_CAP     = 60 * 60
EXTEND_SECS  = 15 * 60
EXTEND_WHEN  = 30 * 60

NC_CHALLENGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'instance', 'nc_challenges'
)

# (challenge_id, user_id) -> {
#   'proc': Popen, 'port': int, 'binary_path': str,
#   'expires_at': float, 'launched_at': float
# }
_running: dict[tuple[int, int], dict] = {}
_lock = threading.Lock()

def _generate_flag() -> str:
    body = hashlib.md5(secrets.token_bytes(16)).hexdigest()
    return f'CSIA{{{body}}}'


def _inject_flag(directory: str) -> str | None:
    """
    Overwrite every flag.txt found under directory with a fresh generated flag.
    Returns the flag string, or None if no flag.txt exists.
    """
    flag = None
    for root, _, files in os.walk(directory):
        for f in files:
            if f == 'flag.txt':
                if flag is None:
                    flag = _generate_flag()
                with open(os.path.join(root, f), 'w') as fh:
                    fh.write(flag + '\n')
    return flag


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    used = {v['port'] for v in _running.values()}
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port not in used and _port_is_free(port):
            return port
    raise RuntimeError('No free ports available in the RE challenge range.')


def _wait_for_port(port: int, timeout: float = 6.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ── Sandbox ──────────────────────────────────────────────────────────────────

# UID of the ctf-sandbox user created in the Dockerfile
_SANDBOX_UID = 1500
_SANDBOX_GID = 1500

# Per-connection resource limits
_MAX_PIDS    = 32       # max processes/threads per connection
_MAX_MEM_MB  = 128      # virtual memory cap in MB
_CPU_MS      = 60_000   # 60 seconds of CPU time per connection
_WALL_SECS   = 120      # 2 minutes wall-clock per connection before nsjail kills it


def _nsjail_cmd(entrypoint: str, work_dir: str) -> list[str]:
    """
    Build the nsjail argv that wraps one challenge execution.
    Isolation:
      - Host rootfs bind-mounted read-only (bash, cat, etc. are available)
      - work_dir bind-mounted read-write on top (challenge files writable)
      - No new network namespace so socat fd stays valid
      - Runs as ctf-sandbox uid 1500
      - Limits: 32 PIDs, 128 MB RAM, 60 s CPU, 120 s wall-clock
    """
    return [
        'nsjail',
        '--mode', 'o',
        '--chroot', '/',                        # host rootfs as read-only base
        '--user', str(_SANDBOX_UID),
        '--group', str(_SANDBOX_GID),
        '--disable_clone_newnet',
        '--rlimit_as', str(_MAX_MEM_MB),
        '--rlimit_cpu', str(_CPU_MS // 1000),
        '--rlimit_nproc', str(_MAX_PIDS),
        '--time_limit', str(_WALL_SECS),
        '--log_fd', '2',
        '--bindmount', f'{work_dir}:{work_dir}:rw',  # challenge files writable
        '--cwd', work_dir,
        '--',
        '/bin/bash', entrypoint,                    # run script via bash
    ]


# Priority order when searching for an entry point inside an archive
_ENTRYPOINT_NAMES = ('run', 'main', 'challenge', 'start', 'server')


def _find_entrypoint(directory: str) -> str:
    """
    Find the executable entry point inside an extracted archive directory.
    Priority:
      1. Any file named run, main, challenge, start, server (with or without extension)
      2. The only executable file in the root
      3. The only file in the root
    Raises RuntimeError if nothing suitable is found.
    """
    root_files = [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    ]
    # Priority 1 — well-known entry point names
    for name in _ENTRYPOINT_NAMES:
        for f in root_files:
            if os.path.splitext(f)[0].lower() == name:
                return os.path.join(directory, f)
    # Priority 2 — only executable in root
    executables = [
        f for f in root_files
        if os.access(os.path.join(directory, f), os.X_OK)
    ]
    if len(executables) == 1:
        return os.path.join(directory, executables[0])
    # Priority 3 — only file in root
    if len(root_files) == 1:
        return os.path.join(directory, root_files[0])
    raise RuntimeError(
        'Could not determine entry point. Name your main executable '
        '"run", "main", or "challenge".'
    )


def _deploy_binary(stored_path: str, challenge_id: int, user_id: int) -> tuple[str, str]:
    """
    Prepare a per-user working directory and return (entrypoint_path, working_dir).
    Handles both a raw executable and a .tar.gz archive.
    """
    deploy_dir = os.path.join(NC_CHALLENGES_DIR, f'bin_{challenge_id}_u{user_id}')
    if os.path.exists(deploy_dir):
        shutil.rmtree(deploy_dir)
    os.makedirs(deploy_dir, exist_ok=True)

    if stored_path.endswith('.tar.gz') or stored_path.endswith('.tgz'):
        # Extract archive — same path-safety logic as web_runner
        with tarfile.open(stored_path, 'r:gz') as tf:
            members = []
            for m in tf.getmembers():
                m.name = os.path.normpath(m.name).lstrip('/')
                if '..' in m.name or m.name.startswith('/'):
                    continue
                members.append(m)
            tf.extractall(deploy_dir, members=members)
        # Unwrap single top-level subdirectory if present
        entries = os.listdir(deploy_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(deploy_dir, entries[0])):
            work_dir = os.path.join(deploy_dir, entries[0])
        else:
            work_dir = deploy_dir
        entrypoint = _find_entrypoint(work_dir)
    else:
        # Raw single file
        binary_name = os.path.basename(stored_path)
        entrypoint = os.path.join(deploy_dir, binary_name)
        shutil.copy2(stored_path, entrypoint)
        work_dir = deploy_dir

    # Ensure the entry point is executable
    current = os.stat(entrypoint).st_mode
    os.chmod(entrypoint, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return entrypoint, work_dir


def _kill_instance(key: tuple[int, int], info: dict):
    try:
        info['proc'].terminate()
        info['proc'].wait(timeout=5)
    except Exception:
        try:
            info['proc'].kill()
        except Exception:
            pass
    deploy_dir = os.path.join(NC_CHALLENGES_DIR, f'bin_{key[0]}_u{key[1]}')
    if os.path.exists(deploy_dir):
        shutil.rmtree(deploy_dir, ignore_errors=True)


def _reaper():
    while True:
        time.sleep(30)
        now = time.time()
        expired = []
        with _lock:
            for key, info in list(_running.items()):
                if now >= info['expires_at'] or info['proc'].poll() is not None:
                    expired.append((key, info))
                    del _running[key]
        for key, info in expired:
            _kill_instance(key, info)


threading.Thread(target=_reaper, daemon=True, name='nc-reaper').start()


# ── Public API ────────────────────────────────────────────────────────────────

def start_nc_server(challenge_id: int, user_id: int, binary_path: str) -> tuple[int, float]:
    """
    Deploy binary and start a per-user socat listener.
    Returns (port, expires_at).
    Idempotent — returns existing instance if still alive.
    """
    key = (challenge_id, user_id)
    with _lock:
        info = _running.get(key)
        if info and info['proc'].poll() is None and time.time() < info['expires_at']:
            return info['port'], info['expires_at'], info.get('dynamic_flag')
        if info:
            _kill_instance(key, info)
            del _running[key]
        port = _free_port()
        _running[key] = {'port': port, 'proc': None, 'binary_path': '', 'expires_at': 0, 'launched_at': 0, 'dynamic_flag': None}

    entrypoint, work_dir = _deploy_binary(binary_path, challenge_id, user_id)
    dynamic_flag = _inject_flag(work_dir)

    # Each socat connection forks and execs nsjail, which in turn execs the
    # challenge binary inside a fully isolated namespace.
    nsjail_argv = _nsjail_cmd(entrypoint, work_dir)

    # Write a wrapper script so socat doesn't have to parse a complex
    # command string — avoids all quoting/escaping issues with EXEC:/SYSTEM:
    wrapper = os.path.join(work_dir, '.run_challenge.sh')
    with open(wrapper, 'w') as wf:
        wf.write('#!/bin/sh\n')
        wf.write(' '.join(shlex.quote(a) for a in nsjail_argv) + '\n')
    os.chmod(wrapper, 0o755)

    proc = subprocess.Popen(
        ['socat',
         f'TCP-LISTEN:{port},reuseaddr,fork',
         f'EXEC:{wrapper},stderr,setsid'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=work_dir,
    )

    now = time.time()
    expires_at = now + INITIAL_TTL

    with _lock:
        _running[key] = {
            'proc': proc,
            'port': port,
            'binary_path': entrypoint,
            'expires_at': expires_at,
            'launched_at': now,
            'dynamic_flag': dynamic_flag,
        }

    if not _wait_for_port(port, timeout=6.0):
        with _lock:
            _running.pop(key, None)
        proc.kill()
        _kill_instance(key, {'proc': proc, 'binary_path': entrypoint})
        raise RuntimeError(f'socat listener for challenge {challenge_id} did not start within 6 seconds.')

    return port, expires_at, dynamic_flag


def extend_nc_server(challenge_id: int, user_id: int) -> tuple[bool, str, float]:
    """
    Extend TTL by EXTEND_SECS when ≤ 30 min remain, capped at 60 min from launch.
    Returns (ok, error_message, new_expires_at).
    """
    key = (challenge_id, user_id)
    with _lock:
        info = _running.get(key)
        if not info or info['proc'].poll() is not None:
            return False, 'No running instance found.', 0.0

        now = time.time()
        remaining = info['expires_at'] - now
        if remaining > EXTEND_WHEN:
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            return False, f'Extension only available when ≤ 30 minutes remain (currently {mins}m {secs}s left).', info['expires_at']

        hard_deadline = info['launched_at'] + HARD_CAP
        new_expires = min(info['expires_at'] + EXTEND_SECS, hard_deadline)
        if new_expires <= info['expires_at'] + 5:
            return False, 'Maximum session time of 60 minutes has been reached.', info['expires_at']

        info['expires_at'] = new_expires
        return True, '', new_expires


def stop_nc_server(challenge_id: int, user_id: int):
    key = (challenge_id, user_id)
    with _lock:
        info = _running.pop(key, None)
    if info:
        _kill_instance(key, info)


def nc_server_status(challenge_id: int, user_id: int) -> dict:
    key = (challenge_id, user_id)
    with _lock:
        info = _running.get(key)

    if info and info['proc'] is not None and info['proc'].poll() is None:
        now = time.time()
        if now < info['expires_at']:
            return {
                'running': True,
                'port': info['port'],
                'expires_at': info['expires_at'],
                'remaining': int(info['expires_at'] - now),
                'can_extend': (info['expires_at'] - now) <= EXTEND_WHEN,
                'at_hard_cap': (info['launched_at'] + HARD_CAP - now) <= 60,
            }

    with _lock:
        _running.pop(key, None)
    return {'running': False, 'port': None, 'expires_at': None, 'remaining': None, 'can_extend': False, 'at_hard_cap': False}


def cleanup_nc_dir(challenge_id: int):
    """Kill ALL user instances for a challenge (called on challenge delete)."""
    to_kill = []
    with _lock:
        for key in list(_running.keys()):
            if key[0] == challenge_id:
                to_kill.append((key, _running.pop(key)))
    for key, info in to_kill:
        _kill_instance(key, info)
    for d in glob.glob(os.path.join(NC_CHALLENGES_DIR, f'bin_{challenge_id}_u*')):
        shutil.rmtree(d, ignore_errors=True)
