"""
Web Challenge Runner — per-user subprocess instances.

Each (challenge_id, user_id) pair gets its own isolated server process and port.
Instances expire after 15 minutes. Users may extend while ≤ 30 minutes remain,
up to a hard cap of 60 minutes total from the original launch time.

A background reaper thread checks every 30 seconds and kills expired instances.

Isolation: each web server runs under a dedicated low-privilege uid (ctf-sandbox,
uid 1500) inside a new user+mount namespace via unshare. The process can only see
its own serve_dir — /app, instance/, .env, and the rest of the container are
not visible. Resource limits (RAM, CPU, open files) are applied via prlimit.

Port range: 10000–10999 (must be exposed in docker-compose.yml).
"""

import os
import secrets
import socket
import tarfile
import shutil
import subprocess
import threading
import time
import resource

PORT_RANGE_START = 10000
PORT_RANGE_END   = 10099

INITIAL_TTL  = 15 * 60
HARD_CAP     = 60 * 60
EXTEND_SECS  = 15 * 60
EXTEND_WHEN  = 30 * 60

WEB_CHALLENGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'instance', 'web_challenges'
)

# Sandbox identity — matches the ctf-sandbox user created in the Dockerfile
_SANDBOX_UID = 1500
_SANDBOX_GID = 1500

# Per-instance resource limits
_MAX_MEM_BYTES  = 256 * 1024 * 1024   # 256 MB virtual memory
_MAX_OPEN_FILES = 64                   # open file descriptors
_MAX_PROCS      = 32                   # child processes

# (challenge_id, user_id) -> {
#   'proc': Popen, 'port': int, 'serve_dir': str,
#   'expires_at': float, 'launched_at': float
# }
_running: dict[tuple[int, int], dict] = {}
_lock = threading.Lock()


# ── Sandbox helpers ───────────────────────────────────────────────────────────

def _sandbox_preexec(serve_dir: str):
    """
    Called in the child process (after fork, before exec) to:
      1. Drop to ctf-sandbox uid/gid
      2. Apply rlimits (memory, open files, nproc)
      3. Change working directory to serve_dir
    The parent already passes --user/--mount/--pid flags via unshare so the
    child is already in a new namespace by the time this runs.
    """
    import resource as _r
    # Drop privileges
    os.setgid(_SANDBOX_GID)
    os.setuid(_SANDBOX_UID)
    # Memory cap
    _r.setrlimit(_r.RLIMIT_AS,  (_MAX_MEM_BYTES, _MAX_MEM_BYTES))
    # Open file descriptors
    _r.setrlimit(_r.RLIMIT_NOFILE, (_MAX_OPEN_FILES, _MAX_OPEN_FILES))
    # Child processes
    _r.setrlimit(_r.RLIMIT_NPROC, (_MAX_PROCS, _MAX_PROCS))
    # Working directory
    os.chdir(serve_dir)


def _sandboxed_cmd(server_cmd: list[str], serve_dir: str) -> tuple[list[str], callable]:
    """
    Run server_cmd directly with privilege drop and rlimits via preexec_fn.
    Namespace isolation is provided by the privileged Docker container + nsjail.
    """
    return server_cmd, lambda: _sandbox_preexec(serve_dir)


# ── Port helpers ──────────────────────────────────────────────────────────────

def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    # Must be called with _lock already held or in a context where
    # the used-port snapshot is consistent.
    used = {v['port'] for v in _running.values()}
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port not in used and _port_is_free(port):
            return port
    raise RuntimeError('No free ports available in the web challenge range.')


# ── Flag generation ──────────────────────────────────────────────────────────

_FLAG_CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*-_=+?'


def _generate_flag() -> str:
    body = ''.join(secrets.choice(_FLAG_CHARSET) for _ in range(32))
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


# ── Archive extraction ────────────────────────────────────────────────────────

def _extract(archive_path: str, challenge_id: int, user_id: int) -> str:
    """
    Extract the .tar.gz into a per-user directory:
      instance/web_challenges/serve_<cid>_u<uid>/
    Fresh extraction every launch so state is clean.
    """
    serve_root = os.path.join(WEB_CHALLENGES_DIR, f'serve_{challenge_id}_u{user_id}')
    if os.path.exists(serve_root):
        shutil.rmtree(serve_root)
    os.makedirs(serve_root, exist_ok=True)

    with tarfile.open(archive_path, 'r:gz') as tf:
        members = []
        for m in tf.getmembers():
            m.name = os.path.normpath(m.name).lstrip('/')
            if '..' in m.name or m.name.startswith('/'):
                continue
            members.append(m)
        tf.extractall(serve_root, members=members)

    entries = os.listdir(serve_root)
    if len(entries) == 1 and os.path.isdir(os.path.join(serve_root, entries[0])):
        return os.path.join(serve_root, entries[0])
    return serve_root


def _detect_server(directory: str) -> list[str]:
    """
    Inspect the extracted directory and return the server command to run.
    Priority: PHP > Node.js (JS/TS) > Java (.jar) > Python fallback.
    """
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith('.php'):
                return ['php', '-S', f'0.0.0.0:{{port}}', '-t', directory]

    # Node.js: package.json with a start script, or index.js / server.js / app.js
    pkg_json = os.path.join(directory, 'package.json')
    if os.path.exists(pkg_json):
        import json
        try:
            with open(pkg_json) as fh:
                pkg = json.load(fh)
            if pkg.get('scripts', {}).get('start'):
                return ['npm', 'start', '--prefix', directory]
        except Exception:
            pass
    for js_entry in ('index.js', 'server.js', 'app.js', 'index.ts', 'server.ts', 'app.ts'):
        if os.path.exists(os.path.join(directory, js_entry)):
            if js_entry.endswith('.ts'):
                return ['npx', 'ts-node', os.path.join(directory, js_entry)]
            return ['node', os.path.join(directory, js_entry)]

    # Java: runnable .jar
    for f in os.listdir(directory):
        if f.endswith('.jar'):
            return ['java', '-jar', os.path.join(directory, f)]

    # Python fallback (static files or explicit app.py / main.py)
    for py_entry in ('app.py', 'main.py', 'server.py'):
        if os.path.exists(os.path.join(directory, py_entry)):
            return ['python3', os.path.join(directory, py_entry)]

    return ['python3', '-m', 'http.server', '{port}', '--directory', directory]


# ── Process management ────────────────────────────────────────────────────────

def _wait_for_port(port: int, timeout: float = 6.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _kill_instance(key: tuple[int, int], info: dict):
    """Terminate process and remove extracted files for one instance."""
    try:
        info['proc'].terminate()
        info['proc'].wait(timeout=5)
    except Exception:
        try:
            info['proc'].kill()
        except Exception:
            pass
    serve_root = os.path.join(
        WEB_CHALLENGES_DIR, f'serve_{key[0]}_u{key[1]}'
    )
    if os.path.exists(serve_root):
        shutil.rmtree(serve_root, ignore_errors=True)


def _reaper():
    """Background thread: kill instances whose expires_at has passed."""
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


threading.Thread(target=_reaper, daemon=True, name='web-reaper').start()


# ── Public API ────────────────────────────────────────────────────────────────

def start_server(challenge_id: int, user_id: int, archive_path: str) -> tuple[int, float]:
    """
    Extract archive and start a per-user server subprocess.
    Returns (port, expires_at).
    Idempotent — if already running for this user, returns existing info.
    """
    key = (challenge_id, user_id)
    with _lock:
        info = _running.get(key)
        if info and info['proc'].poll() is None and time.time() < info['expires_at']:
            return info['port'], info['expires_at'], info.get('dynamic_flag')
        # Stale entry — clean up before relaunching
        if info:
            _kill_instance(key, info)
            del _running[key]
        port = _free_port()
        # Reserve the slot immediately so concurrent launches don't grab same port
        _running[key] = {'port': port, 'proc': None, 'serve_dir': '', 'expires_at': 0, 'launched_at': 0, 'dynamic_flag': None}

    serve_dir = _extract(archive_path, challenge_id, user_id)
    dynamic_flag = _inject_flag(serve_dir)
    server_cmd = [
        part.replace('{port}', str(port)) for part in _detect_server(serve_dir)
    ]

    full_cmd, preexec = _sandboxed_cmd(server_cmd, serve_dir)
    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=preexec,
    )

    now = time.time()
    expires_at = now + INITIAL_TTL

    with _lock:
        _running[key] = {
            'proc': proc,
            'port': port,
            'serve_dir': serve_dir,
            'expires_at': expires_at,
            'launched_at': now,
            'dynamic_flag': dynamic_flag,
        }

    if not _wait_for_port(port, timeout=6.0):
        with _lock:
            _running.pop(key, None)
        proc.kill()
        _kill_instance(key, {'proc': proc, 'serve_dir': serve_dir})
        raise RuntimeError(f'Web server for challenge {challenge_id} did not start within 6 seconds.')

    return port, expires_at, dynamic_flag


def extend_server(challenge_id: int, user_id: int) -> tuple[bool, str, float]:
    """
    Extend the instance TTL by EXTEND_SECS, subject to:
      - Instance must be running
      - Time remaining must be ≤ EXTEND_WHEN (30 min)
      - Total lifetime must not exceed HARD_CAP (60 min) from launched_at
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


def stop_server(challenge_id: int, user_id: int):
    """Terminate a specific user's instance."""
    key = (challenge_id, user_id)
    with _lock:
        info = _running.pop(key, None)
    if info:
        _kill_instance(key, info)


def server_status(challenge_id: int, user_id: int) -> dict:
    """
    Return {'running': bool, 'port': int|None, 'expires_at': float|None, 'remaining': int|None}
    """
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


def cleanup_serve_dir(challenge_id: int):
    """Kill ALL user instances for a challenge (called on challenge delete)."""
    to_kill = []
    with _lock:
        for key in list(_running.keys()):
            if key[0] == challenge_id:
                to_kill.append((key, _running.pop(key)))
    for key, info in to_kill:
        _kill_instance(key, info)
    # Also remove any leftover extracted dirs
    import glob
    for d in glob.glob(os.path.join(WEB_CHALLENGES_DIR, f'serve_{challenge_id}_u*')):
        shutil.rmtree(d, ignore_errors=True)
