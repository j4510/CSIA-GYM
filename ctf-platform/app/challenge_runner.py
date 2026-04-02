"""
challenge_runner.py
====================
Thin HTTP client that talks to the runner sidecar (port 32526).
Replaces nc_runner.py and web_runner.py entirely.
"""

import os
import requests

_RUNNER_URL    = os.environ.get("RUNNER_URL", "http://runner:32526")
_RUNNER_SECRET = os.environ.get("RUNNER_SECRET", "")
_TIMEOUT       = 60   # seconds — image pulls can be slow on first launch


def _headers() -> dict:
    return {"X-Runner-Secret": _RUNNER_SECRET}


def _post(path: str, body: dict = None, **params):
    try:
        r = requests.post(f"{_RUNNER_URL}{path}", json=body, params=params or None, headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Runner service is unavailable. Please try again shortly.")


def _get(path: str, **params):
    try:
        r = requests.get(f"{_RUNNER_URL}{path}", params=params, headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"running": False, "port": None, "subdomain": None, "expires_at": None,
                "remaining": None, "can_extend": False, "at_hard_cap": False, "dynamic_flag": None}


# ── Web challenges ────────────────────────────────────────────────────────────

def start_server(challenge_id: int, user_id: int, archive_path: str):
    """Returns (port, subdomain, expires_at, dynamic_flag)."""
    d = _post("/launch", body={
        "challenge_id": challenge_id,
        "user_id": user_id,
        "archive_path": archive_path,
        "challenge_type": "web",
    })
    return d["port"], d["subdomain"], d["expires_at"], d.get("dynamic_flag")


def stop_server(challenge_id: int, user_id: int):
    _post("/stop", challenge_id=challenge_id, user_id=user_id)


def extend_server(challenge_id: int, user_id: int):
    d = _post("/extend", challenge_id=challenge_id, user_id=user_id)
    return d["ok"], d["error"], d["expires_at"]


def server_status(challenge_id: int, user_id: int) -> dict:
    return _get("/status", challenge_id=challenge_id, user_id=user_id)


# ── NC / pwn challenges ───────────────────────────────────────────────────────

def start_nc_server(challenge_id: int, user_id: int, binary_path: str):
    """Returns (port, subdomain, expires_at, dynamic_flag)."""
    d = _post("/launch", body={
        "challenge_id": challenge_id,
        "user_id": user_id,
        "archive_path": binary_path,
        "challenge_type": "nc",
    })
    return d["port"], d["subdomain"], d["expires_at"], d.get("dynamic_flag")


def stop_nc_server(challenge_id: int, user_id: int):
    _post("/stop", challenge_id=challenge_id, user_id=user_id)


def extend_nc_server(challenge_id: int, user_id: int):
    d = _post("/extend", challenge_id=challenge_id, user_id=user_id)
    return d["ok"], d["error"], d["expires_at"]


def nc_server_status(challenge_id: int, user_id: int) -> dict:
    return _get("/status", challenge_id=challenge_id, user_id=user_id)


# ── Shared ────────────────────────────────────────────────────────────────────

def cleanup_challenge(challenge_id: int):
    """Kill all instances for a challenge (called on delete)."""
    _post("/cleanup", challenge_id=challenge_id)
