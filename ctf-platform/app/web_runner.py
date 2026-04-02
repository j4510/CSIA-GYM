"""
Web Challenge Runner — shared base extraction, per-user isolated processes.

Architecture
------------
                    ┌─────────────────────────────────┐
  archive.tar.gz ──▶│  base_<cid>/   (read-only copy) │
                    └──────────┬──────────────────────┘
                               │  shutil.copytree (fast)
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        user_<cid>_u1/   user_<cid>_u2/   user_<cid>_u3/
        own process       own process       own process
        own port          own port          own port
        own DB/state      own DB/state      own DB/state
        own flag.txt      own flag.txt      own flag.txt

- The archive is extracted ONCE into base_<cid>/.
- Each user gets a fast directory copy (copytree) of the base.
- Each user copy gets its own dynamic flag injected into flag.txt.
- Each user runs their own isolated server process on their own port.
- No shared state between users — databases, sessions, files are all separate.

TTL / lifecycle
---------------
- Each (challenge_id, user_id) instance has its own expires_at.
- Users can extend while ≤ 30 min remain, up to a 60-min hard cap.
- The reaper kills expired instances every 30 seconds.

Port range: 10000–10099 (must be exposed in docker-compose.yml).
"""

import os
import secrets
import hashlib
import socket
import tarfile
import shutil
import subprocess
import threading
import time

PORT_RANGE_START = 10000
PORT_RANGE_END   = 10099

INITIAL_TTL  = 15 * 60
HARD_CAP     = 60 * 60
EXTEND_SECS  = 15 * 60
EXTEND_WHEN  = 30 * 60

WEB_CHALLENGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'instance', 'web_challenges'
)

_SANDBOX_UID = 1500
_SANDBOX_GID = 1500

_MAX_MEM_BYTES  = 256 * 1024 * 1024
_MAX_OPEN_FILES = 64
_MAX_PROCS      = 32

# (challenge_id, user_id) -> {
#   'proc': Popen, 'port': int, 'serve_dir': str,
#   'expires_at': float, 'launched_at': float,
#   'dynamic_flag': str | None,
# }
_running: dict[tuple[int, int], dict] = {}
_lock = threading.Lock()


# ── Sandbox ───────────────────────────────────────────────────────────────────

def _sandbox_preexec(serve_dir: str):
    import resource as _r
    os.setgid(_SANDBOX_GID)
    os.setuid(_SANDBOX_UID)
    _r.setrlimit(_r.RLIMIT_AS,     (_MAX_MEM_BYTES,  _MAX_MEM_BYTES))
    _r.setrlimit(_r.RLIMIT_NOFILE, (_MAX_OPEN_FILES, _MAX_OPEN_FILES))
    _r.setrlimit(_r.RLIMIT_NPROC,  (_MAX_PROCS,      _MAX_PROCS))
    os.chdir(serve_dir)


def _sandboxed_cmd(cmd: list[str], serve_dir: str) -> tuple[list[str], callable]:
    return cmd, lambda: _sandbox_preexec(serve_dir)


# ── Port helpers ──────────────────────────────────────────────────────────────

def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    # Must be called with _lock held
    used = {v['port'] for v in _running.values()}
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port not in used and _port_is_free(port):
            return port
    raise RuntimeError('No free ports available in the web challenge range.')


# ── Flag helpers ──────────────────────────────────────────────────────────────

def _generate_flag() -> str:
    body = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    return f'CSIA{{{body}}}'


def _inject_flag(directory: str, flag: str):
    """Write flag into every flag.txt found under directory."""
    real_base = os.path.realpath(directory)
    for dirpath, _dirs, files, dirfd in os.fwalk(real_base):
        if 'flag.txt' not in files:
            continue
        verified = os.path.realpath(dirpath + os.sep + 'flag.txt')
        if not verified.startswith(real_base + os.sep):
            continue
        try:
            fd = os.open('flag.txt', os.O_WRONLY | os.O_TRUNC, dir_fd=dirfd)
            with os.fdopen(fd, 'w') as fh:
                fh.write(flag + '\n')
        except OSError:
            continue


# ── Archive helpers ───────────────────────────────────────────────────────────

def _safe_join(base: str, path: str) -> str:
    real_base = os.path.realpath(base)
    clean = os.path.normpath(path).lstrip(os.sep)
    real_path = os.path.realpath(real_base + os.sep + clean)
    if not real_path.startswith(real_base + os.sep) and real_path != real_base:
        raise ValueError(f'Path traversal: {path!r} escapes {base!r}')
    return real_path


def _safe_tar_members(tf: tarfile.TarFile, dest: str) -> list:
    real_dest = os.path.realpath(dest)
    safe = []
    for m in tf.getmembers():
        m.name = os.path.normpath(m.name).lstrip('/')
        if not m.name or m.name.startswith('/') or '..' in m.name.split(os.sep):
            continue
        safe_name = os.path.basename(m.name)
        if not safe_name:
            continue
        real_member = os.path.realpath(real_dest + os.sep + safe_name)
        if not real_member.startswith(real_dest + os.sep) and real_member != real_dest:
            continue
        m.name = safe_name
        safe.append(m)
    return safe


def _ensure_base(archive_path: str, challenge_id: int) -> str:
    """
    Extract archive into base_<cid>/ exactly once.
    Returns the path to the extracted base directory.
    Re-extracts only if the base directory is missing.
    """
    real_web_dir = os.path.realpath(WEB_CHALLENGES_DIR)
    cid = abs(int(challenge_id))
    base_name = 'base_{:d}'.format(cid)
    base_root = os.path.realpath(real_web_dir + os.sep + base_name)
    if not base_root.startswith(real_web_dir + os.sep):
        raise ValueError('Invalid base directory')

    if os.path.exists(base_root):
        return base_root  # Already extracted — reuse

    os.makedirs(base_root, exist_ok=True)
    with tarfile.open(archive_path, 'r:gz') as tf:
        for m in _safe_tar_members(tf, base_root):
            tf.extract(m, base_root, set_attrs=False)

    # Unwrap single top-level directory if present
    entries = os.listdir(base_root)
    if len(entries) == 1 and os.path.isdir(_safe_join(base_root, entries[0])):
        inner = _safe_join(base_root, entries[0])
        # Move contents up one level
        tmp = base_root + '_tmp'
        os.rename(inner, tmp)
        shutil.rmtree(base_root)
        os.rename(tmp, base_root)

    return base_root


def _make_user_copy(base_dir: str, challenge_id: int, user_id: int) -> str:
    """
    Copy base_<cid>/ into user_<cid>_u<uid>/ for an isolated per-user instance.
    Removes any previous copy first so state is always clean on relaunch.
    """
    real_web_dir = os.path.realpath(WEB_CHALLENGES_DIR)
    cid = abs(int(challenge_id))
    uid = abs(int(user_id))
    dir_name = 'user_{:d}_u{:d}'.format(cid, uid)
    user_root = os.path.realpath(real_web_dir + os.sep + dir_name)
    if not user_root.startswith(real_web_dir + os.sep):
        raise ValueError('Invalid user directory')
    if os.path.exists(user_root):
        shutil.rmtree(user_root)
    shutil.copytree(base_dir, user_root)
    return user_root


# ── Server detection ──────────────────────────────────────────────────────────

def _detect_server(directory: str) -> list[str]:
    real_dir = os.path.realpath(directory)

    for root, _, files in os.walk(real_dir):
        if not os.path.realpath(root).startswith(real_dir):
            continue
        for f in files:
            if f.endswith('.php'):
                return ['php', '-S', '0.0.0.0:{port}', '-t', real_dir]

    pkg_json = os.path.realpath(real_dir + os.sep + 'package.json')
    if pkg_json.startswith(real_dir + os.sep) and os.path.exists(pkg_json):
        import json
        try:
            with open(pkg_json) as fh:
                pkg = json.load(fh)
            if pkg.get('scripts', {}).get('start'):
                return ['npm', 'start', '--prefix', real_dir]
        except (OSError, ValueError):
            pass

    for js_entry in ('index.js', 'server.js', 'app.js', 'index.ts', 'server.ts', 'app.ts'):
        entry_path = os.path.realpath(real_dir + os.sep + js_entry)
        if entry_path.startswith(real_dir + os.sep) and os.path.exists(entry_path):
            return ['npx', 'ts-node', entry_path] if js_entry.endswith('.ts') else ['node', entry_path]

    try:
        dir_entries = os.listdir(real_dir)
    except OSError:
        dir_entries = []
    for f in dir_entries:
        if f.endswith('.jar'):
            jar_path = os.path.realpath(real_dir + os.sep + f)
            if jar_path.startswith(real_dir + os.sep):
                return ['java', '-jar', jar_path]

    for py_entry in ('app.py', 'main.py', 'server.py'):
        py_path = os.path.realpath(real_dir + os.sep + py_entry)
        if py_path.startswith(real_dir + os.sep) and os.path.exists(py_path):
            return ['python3', py_path]

    return ['python3', '-m', 'http.server', '{port}', '--directory', real_dir]


_ALLOWED_EXECUTABLES = frozenset({
    'php', 'node', 'npx', 'npm', 'java', 'python3', 'ts-node',
})


def _validate_cmd(cmd: list[str], serve_dir: str) -> list[str]:
    if not cmd:
        raise ValueError('Empty command')
    executable = cmd[0]
    allowed_abs = {
        '/usr/bin/php', '/usr/bin/node', '/usr/bin/npx', '/usr/bin/npm',
        '/usr/bin/java', '/usr/bin/python3', '/usr/local/bin/python3',
        '/usr/bin/ts-node', '/usr/local/bin/ts-node',
        '/usr/local/bin/npx', '/usr/local/bin/npm', '/usr/local/bin/node',
    }
    if os.path.basename(executable) not in _ALLOWED_EXECUTABLES and executable not in allowed_abs:
        raise ValueError(f'Executable not in allowlist: {executable!r}')
    real_serve = os.path.realpath(serve_dir)
    validated = [executable]
    for arg in cmd[1:]:
        if os.path.isabs(arg):
            real_arg = os.path.realpath(arg)
            if not real_arg.startswith(real_serve + os.sep) and real_arg != real_serve:
                raise ValueError(f'Argument escapes serve_dir: {arg!r}')
        validated.append(arg)
    return validated


# ── Process management ────────────────────────────────────────────────────────

def _wait_for_port(port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _kill_instance(key: tuple[int, int], info: dict):
    """Terminate process and remove the user's copy directory."""
    try:
        info['proc'].terminate()
        info['proc'].wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            info['proc'].kill()
        except OSError:
            pass

    real_web_dir = os.path.realpath(WEB_CHALLENGES_DIR)
    try:
        cid = abs(int(key[0]))
        uid = abs(int(key[1]))
    except (TypeError, ValueError):
        return
    dir_name = 'user_{:d}_u{:d}'.format(cid, uid)
    try:
        entries = os.listdir(real_web_dir)
    except OSError:
        return
    for entry in entries:
        if entry != dir_name:
            continue
        serve_root = os.path.realpath(real_web_dir + os.sep + entry)
        if serve_root.startswith(real_web_dir + os.sep) and os.path.exists(serve_root):
            shutil.rmtree(serve_root, ignore_errors=True)
        break


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


threading.Thread(target=_reaper, daemon=True, name='web-reaper').start()


# ── Dynamic flag DB helper ────────────────────────────────────────────────────

def _store_dynamic_flag(challenge_id: int, user_id: int, flag: str):
    try:
        from app import db
        from app.models import DynamicFlag
        existing = DynamicFlag.query.filter_by(
            challenge_id=challenge_id, user_id=user_id
        ).first()
        if existing:
            existing.flag = flag
        else:
            db.session.add(DynamicFlag(
                challenge_id=challenge_id, user_id=user_id, flag=flag
            ))
        db.session.commit()
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def start_server(challenge_id: int, user_id: int, archive_path: str) -> tuple[int, float, str | None]:
    """
    Start an isolated per-user server process for challenge_id.

    - The archive is extracted to base_<cid>/ once (shared, read-only).
    - A fresh copy is made to user_<cid>_u<uid>/ for this user.
    - The user's copy gets its own dynamic flag injected into flag.txt.
    - A new process is started on a free port for this user.

    If the user already has a running instance, returns the existing one.
    Returns (port, expires_at, dynamic_flag).
    """
    key = (int(challenge_id), int(user_id))

    with _lock:
        info = _running.get(key)
        if info and info['proc'].poll() is None and time.time() < info['expires_at']:
            return info['port'], info['expires_at'], info.get('dynamic_flag')
        if info:
            _kill_instance(key, info)
            del _running[key]
        port = _free_port()
        # Reserve slot to prevent concurrent launches grabbing the same port
        _running[key] = {
            'proc': None, 'port': port, 'serve_dir': '',
            'expires_at': 0, 'launched_at': 0, 'dynamic_flag': None,
        }

    # Extract base once (shared), then copy for this user (isolated)
    base_dir  = _ensure_base(archive_path, challenge_id)
    user_dir  = _make_user_copy(base_dir, challenge_id, user_id)

    # Inject a unique flag into this user's copy
    user_flag = _generate_flag()
    _inject_flag(user_dir, user_flag)
    _store_dynamic_flag(challenge_id, user_id, user_flag)

    server_cmd = [
        part.replace('{port}', str(port)) for part in _detect_server(user_dir)
    ]
    try:
        server_cmd = _validate_cmd(server_cmd, user_dir)
    except ValueError as e:
        with _lock:
            _running.pop(key, None)
        shutil.rmtree(user_dir, ignore_errors=True)
        raise RuntimeError(f'Unsafe server command rejected: {e}') from e

    full_cmd, preexec = _sandboxed_cmd(server_cmd, user_dir)
    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=preexec,
        shell=False,
    )

    now = time.time()
    expires_at = now + INITIAL_TTL

    with _lock:
        _running[key] = {
            'proc': proc,
            'port': port,
            'serve_dir': user_dir,
            'expires_at': expires_at,
            'launched_at': now,
            'dynamic_flag': user_flag,
        }

    if not _wait_for_port(port, timeout=8.0):
        with _lock:
            _running.pop(key, None)
        proc.kill()
        _kill_instance(key, {'proc': proc, 'serve_dir': user_dir})
        raise RuntimeError(
            f'Web server for challenge {challenge_id} (user {user_id}) '
            f'did not start within 8 seconds.'
        )

    return port, expires_at, user_flag


def extend_server(challenge_id: int, user_id: int) -> tuple[bool, str, float]:
    key = (int(challenge_id), int(user_id))
    with _lock:
        info = _running.get(key)
        if not info or info['proc'].poll() is not None:
            return False, 'No running instance found.', 0.0

        now = time.time()
        remaining = info['expires_at'] - now
        if remaining > EXTEND_WHEN:
            mins, secs = int(remaining // 60), int(remaining % 60)
            return (
                False,
                f'Extension only available when ≤ 30 minutes remain '
                f'(currently {mins}m {secs}s left).',
                info['expires_at'],
            )

        hard_deadline = info['launched_at'] + HARD_CAP
        new_expires = min(info['expires_at'] + EXTEND_SECS, hard_deadline)
        if new_expires <= info['expires_at'] + 5:
            return False, 'Maximum session time of 60 minutes has been reached.', info['expires_at']

        info['expires_at'] = new_expires
        return True, '', new_expires


def stop_server(challenge_id: int, user_id: int):
    key = (int(challenge_id), int(user_id))
    with _lock:
        info = _running.pop(key, None)
    if info:
        _kill_instance(key, info)


def server_status(challenge_id: int, user_id: int) -> dict:
    key = (int(challenge_id), int(user_id))
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
    return {
        'running': False, 'port': None, 'expires_at': None,
        'remaining': None, 'can_extend': False, 'at_hard_cap': False,
    }


def cleanup_serve_dir(challenge_id: int):
    """Kill ALL user instances for a challenge and remove all directories."""
    cid = int(challenge_id)
    with _lock:
        to_kill = [
            (key, _running.pop(key))
            for key in list(_running.keys()) if key[0] == cid
        ]
    for key, info in to_kill:
        _kill_instance(key, info)

    base_prefix = 'base_{:d}'.format(abs(cid))
    user_prefix  = 'user_{:d}_u'.format(abs(cid))
    try:
        entries = os.listdir(real_web_dir)
    except OSError:
        return
    for entry in entries:
        if entry != base_prefix and not entry.startswith(user_prefix):
            continue
        real_d = os.path.realpath(real_web_dir + os.sep + entry)
        if real_d.startswith(real_web_dir + os.sep):
            shutil.rmtree(real_d, ignore_errors=True)
