"""
Challenge Runner Sidecar — port 32526
======================================
Owns the Docker socket. The main CTF platform talks to this over HTTP
using a shared RUNNER_SECRET for authentication.

Responsibilities:
- Build minimal per-challenge Docker images on first launch (pulled on demand)
- Spin up per-user containers on random ports 10000-11999
- Inject dynamic flag.txt per user
- Auto-kill containers after TTL (15 min default, extendable to 60 min)
- Kill container immediately on solve
- Reap expired containers every 30 seconds

Challenge types (declared by category):
  Web              -> HTTP server, proxied via nginx subdomain+port
  Binary Exploitation -> socat TCP listener, nc host port
"""

import os
import re
import secrets
import hashlib
import socket
import tarfile
import shutil
import threading
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

import docker
import docker.errors
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

RUNNER_SECRET   = os.environ["RUNNER_SECRET"]
CHALLENGES_DIR  = os.environ.get("CHALLENGES_DIR", "/app/instance")
HOST_INSTANCE_DIR = os.environ.get("HOST_INSTANCE_DIR", "/opt/ctf/instance")


def _host_path(container_path: str) -> str:
    """
    Translate a path inside the runner container (/app/instance/...)
    to the equivalent host path (HOST_INSTANCE_DIR/...) so Docker daemon
    can mount it into child containers.
    """
    rel = os.path.relpath(container_path, CHALLENGES_DIR)
    return os.path.join(HOST_INSTANCE_DIR, rel)
PIP_CACHE_DIR   = "/cache/pip"
NPM_CACHE_DIR   = "/cache/npm"

PORT_MIN = 10000
PORT_MAX = 11999

INITIAL_TTL = 15 * 60   # 15 minutes
HARD_CAP    = 60 * 60   # 60 minutes max
EXTEND_SECS = 15 * 60
EXTEND_WHEN = 30 * 60   # can extend when ≤ 30 min remain

SUBDOMAINS = [
    "nathanael.chal.haucsia.com",
    "thomas.chal.haucsia.com",
    "peter.chal.haucsia.com",
    "matthew.chal.haucsia.com",
    "judas.chal.haucsia.com",
    "james.chal.haucsia.com",
    "andrew.chal.haucsia.com",
]

# Per-container resource limits
MEM_LIMIT    = "128m"
CPU_QUOTA    = 25000   # 0.25 CPU (out of 100000 = 1 CPU)
CPU_PERIOD   = 100000
PIDS_LIMIT   = 64

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")

# ── State ─────────────────────────────────────────────────────────────────────
# key: (challenge_id, user_id)
# value: {
#   container_id, port, subdomain, expires_at, launched_at,
#   dynamic_flag, challenge_type
# }
_instances: dict[tuple[int, int], dict] = {}
_lock = threading.Lock()

_docker: docker.DockerClient = None  # initialised in lifespan


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _docker
    _docker = docker.from_env()
    os.makedirs(PIP_CACHE_DIR, exist_ok=True)
    os.makedirs(NPM_CACHE_DIR, exist_ok=True)
    # ── Startup: pre-build ctf-nc-base image with socat ──────────────────────
    try:
        _docker.images.get("ctf-nc-base")
        log.info("ctf-nc-base image already exists.")
    except docker.errors.ImageNotFound:
        log.info("Building ctf-nc-base image...")
        import tempfile
        dockerfile = (
            "FROM debian:bookworm-slim\n"
            "RUN apt-get update -qq && "
            "apt-get install -y -qq --no-install-recommends socat && "
            "rm -rf /var/lib/apt/lists/*\n"
        )
        with tempfile.TemporaryDirectory() as ctx:
            with open(os.path.join(ctx, "Dockerfile"), "w") as f:
                f.write(dockerfile)
            _docker.images.build(path=ctx, tag="ctf-nc-base", rm=True)
        log.info("ctf-nc-base image built.")
    # ── Startup: kill any leftover challenge containers from a previous run ──
    try:
        leftover = _docker.containers.list(filters={"name": "chal_"})
        for c in leftover:
            log.info("Killing leftover container %s", c.name)
            try:
                c.kill()
                c.remove(force=True)
            except Exception:
                pass
    except Exception as e:
        log.warning("Could not clean up leftover containers: %s", e)
    t = threading.Thread(target=_reaper, daemon=True, name="reaper")
    t.start()
    yield
    # ── Shutdown: kill all running challenge containers ────────────────────
    log.info("Runner shutting down — killing all challenge containers...")
    with _lock:
        to_kill = list(_instances.items())
        _instances.clear()
    for key, info in to_kill:
        _kill_instance(key, info)
    log.info("All challenge containers stopped.")
    _docker.close()


app = FastAPI(lifespan=lifespan)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _auth(x_runner_secret: str = Header(...)):
    if not secrets.compare_digest(x_runner_secret, RUNNER_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_flag() -> str:
    body = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    return f"CSIA{{{body}}}"


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    """Must be called with _lock held."""
    used = {v["port"] for v in _instances.values()}
    import random
    candidates = list(range(PORT_MIN, PORT_MAX + 1))
    random.shuffle(candidates)
    for p in candidates:
        if p not in used and _port_free(p):
            return p
    raise RuntimeError("No free ports available (10000-11999)")


def _random_subdomain() -> str:
    import random
    return random.choice(SUBDOMAINS)


def _safe_join(base: str, path: str) -> str:
    real_base = os.path.realpath(base)
    clean = os.path.normpath(path).lstrip(os.sep)
    real_path = os.path.realpath(real_base + os.sep + clean)
    if not real_path.startswith(real_base + os.sep) and real_path != real_base:
        raise ValueError(f"Path traversal: {path!r}")
    return real_path


def _extract_archive(archive_path: str, dest: str):
    """Extract tar.gz safely — no path traversal, flatten single top-level dir."""
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tf:
        for m in tf.getmembers():
            m.name = os.path.normpath(m.name).lstrip("/")
            if not m.name or ".." in m.name.split(os.sep):
                continue
            safe = os.path.realpath(dest + os.sep + m.name)
            if not safe.startswith(os.path.realpath(dest) + os.sep):
                continue
            tf.extract(m, dest, set_attrs=False)
    # Unwrap single top-level directory
    entries = os.listdir(dest)
    if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
        inner = os.path.join(dest, entries[0])
        tmp = dest + "_tmp"
        shutil.copytree(inner, tmp)
        shutil.rmtree(dest)
        os.rename(tmp, dest)


def _inject_flag(directory: str, flag: str):
    """Overwrite every flag.txt found under directory."""
    real_base = os.path.realpath(directory)
    for dirpath, _dirs, files, dirfd in os.fwalk(real_base):
        if "flag.txt" not in files:
            continue
        verified = os.path.realpath(dirpath + os.sep + "flag.txt")
        if not verified.startswith(real_base + os.sep):
            continue
        try:
            fd = os.open("flag.txt", os.O_WRONLY | os.O_TRUNC, dir_fd=dirfd)
            with os.fdopen(fd, "w") as fh:
                fh.write(flag + "\n")
        except OSError:
            continue


def _detect_web_server(directory: str) -> tuple[str, list[str]]:
    """
    Detect the server type and return (image, cmd_template).
    cmd_template may contain {port} placeholder.
    """
    real = os.path.realpath(directory)

    # PHP
    for root, _, files in os.walk(real):
        for f in files:
            if f.endswith(".php"):
                return ("php:8.2-cli-alpine", ["php", "-S", "0.0.0.0:{port}", "-t", "/app"])

    # Node / TypeScript
    pkg = os.path.join(real, "package.json")
    if os.path.exists(pkg):
        import json
        try:
            with open(pkg) as fh:
                data = json.load(fh)
            if data.get("scripts", {}).get("start"):
                return ("node:20-alpine", ["sh", "-c", "npm install --prefer-offline && npm start"])
        except (OSError, ValueError):
            pass
    for js in ("index.js", "server.js", "app.js"):
        if os.path.exists(os.path.join(real, js)):
            return ("node:20-alpine", ["sh", "-c", f"npm install --prefer-offline 2>/dev/null; node {js}"])
    for ts in ("index.ts", "server.ts", "app.ts"):
        if os.path.exists(os.path.join(real, ts)):
            return ("node:20-alpine", ["sh", "-c", f"npm install --prefer-offline 2>/dev/null; npx ts-node {ts}"])

    # Java
    for f in os.listdir(real):
        if f.endswith(".jar"):
            return ("eclipse-temurin:21-jre-alpine", ["java", "-jar", f"/app/{f}"])

    # Python
    for py in ("app.py", "main.py", "server.py"):
        if os.path.exists(os.path.join(real, py)):
            return (
                "python:3.11-alpine",
                ["sh", "-c", "pip install --quiet --no-cache-dir -r requirements.txt 2>/dev/null || true; python " + py],
            )

    # Static fallback
    return ("python:3.11-alpine", ["python", "-m", "http.server", "{port}"])


def _build_web_container(
    challenge_id: int, user_id: int, archive_path: str, port: int, flag: str
) -> str:
    """
    Extract archive into a per-user temp dir, inject flag, spin up container.
    Returns container ID.
    """
    work_dir = os.path.join(CHALLENGES_DIR, f"web_{challenge_id}_u{user_id}")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    _extract_archive(archive_path, work_dir)
    _inject_flag(work_dir, flag)

    image, cmd_template = _detect_web_server(work_dir)
    cmd = [part.replace("{port}", str(port)) for part in cmd_template]

    # Pull image if not present
    try:
        _docker.images.get(image)
    except docker.errors.ImageNotFound:
        log.info("Pulling image %s", image)
        _docker.images.pull(image)

    container = _docker.containers.run(
        image,
        command=cmd,
        detach=True,
        remove=False,
        ports={f"{port}/tcp": ("0.0.0.0", port)},
        volumes={
            _host_path(work_dir): {"bind": "/app", "mode": "rw"},
            PIP_CACHE_DIR: {"bind": "/root/.cache/pip", "mode": "rw"},
            NPM_CACHE_DIR: {"bind": "/root/.npm", "mode": "rw"},
        },
        working_dir="/app",
        mem_limit=MEM_LIMIT,
        cpu_quota=CPU_QUOTA,
        cpu_period=CPU_PERIOD,
        pids_limit=PIDS_LIMIT,
        network_mode="bridge",
        read_only=False,
        name=f"chal_web_{challenge_id}_u{user_id}",
        labels={
            "chal.type": "web",
            "chal.challenge_id": str(challenge_id),
            "chal.user_id": str(user_id),
        },
    )
    return container.id


def _build_nc_container(
    challenge_id: int, user_id: int, archive_path: str, port: int, flag: str
) -> str:
    """
    Extract archive into a per-user temp dir, inject flag, wrap with socat,
    spin up container. Returns container ID.
    """
    work_dir = os.path.join(CHALLENGES_DIR, f"nc_{challenge_id}_u{user_id}")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    _extract_archive(archive_path, work_dir)
    _inject_flag(work_dir, flag)

    # Find entrypoint
    ENTRY_NAMES = ("run", "main", "challenge", "start", "server")
    entrypoint = None
    files = [f for f in os.listdir(work_dir) if os.path.isfile(os.path.join(work_dir, f))]
    for name in ENTRY_NAMES:
        for f in files:
            if os.path.splitext(f)[0].lower() == name:
                entrypoint = f
                break
        if entrypoint:
            break
    if not entrypoint:
        executables = [f for f in files if os.access(os.path.join(work_dir, f), os.X_OK)]
        entrypoint = executables[0] if executables else (files[0] if files else None)
    if not entrypoint:
        raise RuntimeError("Could not find entrypoint in archive")

    # Make executable
    os.chmod(os.path.join(work_dir, entrypoint), 0o755)

    # Write socat wrapper
    wrapper = os.path.join(work_dir, ".run.sh")
    with open(wrapper, "w") as wf:
        wf.write("#!/bin/sh\n")
        wf.write(f"exec /app/{entrypoint}\n")
    os.chmod(wrapper, 0o755)

    cmd = ["socat", f"TCP-LISTEN:{port},reuseaddr,fork", f"EXEC:/app/.run.sh,stderr,setsid"]

    container = _docker.containers.run(
        "ctf-nc-base",
        command=cmd,
        detach=True,
        remove=False,
        ports={f"{port}/tcp": ("0.0.0.0", port)},
        volumes={
            _host_path(work_dir): {"bind": "/app", "mode": "rw"},
        },
        working_dir="/app",
        mem_limit=MEM_LIMIT,
        cpu_quota=CPU_QUOTA,
        cpu_period=CPU_PERIOD,
        pids_limit=PIDS_LIMIT,
        network_mode="bridge",
        name=f"chal_nc_{challenge_id}_u{user_id}",
        labels={
            "chal.type": "nc",
            "chal.challenge_id": str(challenge_id),
            "chal.user_id": str(user_id),
        },
    )
    return container.id


def _kill_instance(key: tuple[int, int], info: dict):
    """Kill container and remove work directory."""
    cid = info.get("container_id")
    if cid:
        try:
            c = _docker.containers.get(cid)
            c.kill()
            c.remove(force=True)
        except docker.errors.NotFound:
            pass
        except Exception as e:
            log.warning("Error killing container %s: %s", cid, e)

    challenge_id, user_id = key
    ctype = info.get("challenge_type", "web")
    work_dir = os.path.join(CHALLENGES_DIR, f"{ctype}_{challenge_id}_u{user_id}")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)


def _reaper():
    while True:
        time.sleep(30)
        now = time.time()
        expired = []
        with _lock:
            for key, info in list(_instances.items()):
                dead = False
                if now >= info["expires_at"]:
                    dead = True
                else:
                    # Check if container is still running
                    try:
                        c = _docker.containers.get(info["container_id"])
                        if c.status not in ("running", "created"):
                            dead = True
                    except docker.errors.NotFound:
                        dead = True
                if dead:
                    expired.append((key, info))
                    del _instances[key]
        for key, info in expired:
            log.info("Reaper killing instance %s", key)
            _kill_instance(key, info)


# ── Request / Response models ─────────────────────────────────────────────────

class LaunchRequest(BaseModel):
    challenge_id: int
    user_id: int
    archive_path: str
    challenge_type: str   # "web" or "nc"


class LaunchResponse(BaseModel):
    port: int
    subdomain: str
    expires_at: float
    dynamic_flag: Optional[str]


class StatusResponse(BaseModel):
    running: bool
    port: Optional[int]
    subdomain: Optional[str]
    expires_at: Optional[float]
    remaining: Optional[int]
    can_extend: bool
    at_hard_cap: bool
    dynamic_flag: Optional[str]


class ExtendResponse(BaseModel):
    ok: bool
    error: str
    expires_at: float


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/launch", response_model=LaunchResponse, dependencies=[Depends(_auth)])
def launch(req: LaunchRequest):
    key = (req.challenge_id, req.user_id)
    ctype = req.challenge_type.lower()
    if ctype not in ("web", "nc"):
        raise HTTPException(400, "challenge_type must be 'web' or 'nc'")

    with _lock:
        info = _instances.get(key)
        if info and time.time() < info["expires_at"]:
            # Check container still alive
            try:
                c = _docker.containers.get(info["container_id"])
                if c.status == "running":
                    return LaunchResponse(
                        port=info["port"],
                        subdomain=info["subdomain"],
                        expires_at=info["expires_at"],
                        dynamic_flag=info.get("dynamic_flag"),
                    )
            except docker.errors.NotFound:
                pass
            # Stale — clean up
            _kill_instance(key, info)
            del _instances[key]

        port = _free_port()
        subdomain = _random_subdomain()
        # Reserve slot
        _instances[key] = {
            "container_id": None, "port": port, "subdomain": subdomain,
            "expires_at": 0, "launched_at": 0,
            "dynamic_flag": None, "challenge_type": ctype,
        }

    flag = _generate_flag()
    try:
        if ctype == "web":
            container_id = _build_web_container(
                req.challenge_id, req.user_id, req.archive_path, port, flag
            )
        else:
            container_id = _build_nc_container(
                req.challenge_id, req.user_id, req.archive_path, port, flag
            )
    except Exception as e:
        with _lock:
            _instances.pop(key, None)
        log.exception("Failed to launch instance %s", key)
        raise HTTPException(500, str(e))

    now = time.time()
    expires_at = now + INITIAL_TTL
    with _lock:
        _instances[key] = {
            "container_id": container_id,
            "port": port,
            "subdomain": subdomain,
            "expires_at": expires_at,
            "launched_at": now,
            "dynamic_flag": flag,
            "challenge_type": ctype,
        }

    log.info("Launched %s instance for challenge=%s user=%s port=%s",
             ctype, req.challenge_id, req.user_id, port)
    return LaunchResponse(port=port, subdomain=subdomain, expires_at=expires_at, dynamic_flag=flag)


@app.post("/stop", dependencies=[Depends(_auth)])
def stop(challenge_id: int, user_id: int):
    key = (challenge_id, user_id)
    with _lock:
        info = _instances.pop(key, None)
    if info:
        _kill_instance(key, info)
    return {"ok": True}


@app.post("/extend", response_model=ExtendResponse, dependencies=[Depends(_auth)])
def extend(challenge_id: int, user_id: int):
    key = (challenge_id, user_id)
    with _lock:
        info = _instances.get(key)
        if not info or info["container_id"] is None:
            return ExtendResponse(ok=False, error="No running instance found.", expires_at=0.0)

        now = time.time()
        remaining = info["expires_at"] - now
        if remaining > EXTEND_WHEN:
            mins, secs = int(remaining // 60), int(remaining % 60)
            return ExtendResponse(
                ok=False,
                error=f"Extension only available when ≤ 30 minutes remain (currently {mins}m {secs}s left).",
                expires_at=info["expires_at"],
            )

        hard_deadline = info["launched_at"] + HARD_CAP
        new_expires = min(info["expires_at"] + EXTEND_SECS, hard_deadline)
        if new_expires <= info["expires_at"] + 5:
            return ExtendResponse(ok=False, error="Maximum session time of 60 minutes reached.", expires_at=info["expires_at"])

        info["expires_at"] = new_expires
        return ExtendResponse(ok=True, error="", expires_at=new_expires)


@app.get("/status", response_model=StatusResponse, dependencies=[Depends(_auth)])
def status(challenge_id: int, user_id: int):
    key = (challenge_id, user_id)
    with _lock:
        info = _instances.get(key)

    if not info or info["container_id"] is None:
        return StatusResponse(running=False, port=None, subdomain=None, expires_at=None,
                              remaining=None, can_extend=False, at_hard_cap=False, dynamic_flag=None)

    try:
        c = _docker.containers.get(info["container_id"])
        if c.status != "running":
            with _lock:
                _instances.pop(key, None)
            _kill_instance(key, info)
            return StatusResponse(running=False, port=None, subdomain=None, expires_at=None,
                                  remaining=None, can_extend=False, at_hard_cap=False, dynamic_flag=None)
    except docker.errors.NotFound:
        with _lock:
            _instances.pop(key, None)
        return StatusResponse(running=False, port=None, subdomain=None, expires_at=None,
                              remaining=None, can_extend=False, at_hard_cap=False, dynamic_flag=None)

    now = time.time()
    if now >= info["expires_at"]:
        with _lock:
            _instances.pop(key, None)
        _kill_instance(key, info)
        return StatusResponse(running=False, port=None, subdomain=None, expires_at=None,
                              remaining=None, can_extend=False, at_hard_cap=False, dynamic_flag=None)

    remaining = int(info["expires_at"] - now)
    return StatusResponse(
        running=True,
        port=info["port"],
        subdomain=info["subdomain"],
        expires_at=info["expires_at"],
        remaining=remaining,
        can_extend=remaining <= EXTEND_WHEN,
        at_hard_cap=(info["launched_at"] + HARD_CAP - now) <= 60,
        dynamic_flag=info.get("dynamic_flag"),
    )


@app.post("/cleanup", dependencies=[Depends(_auth)])
def cleanup(challenge_id: int):
    """Kill all instances for a challenge (called on challenge delete)."""
    with _lock:
        to_kill = [(k, _instances.pop(k)) for k in list(_instances) if k[0] == challenge_id]
    for key, info in to_kill:
        _kill_instance(key, info)
    return {"ok": True, "killed": len(to_kill)}


@app.get("/health")
def health():
    return {"ok": True}
