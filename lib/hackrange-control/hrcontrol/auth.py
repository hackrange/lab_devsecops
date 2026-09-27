"""Who may use the control panel.

Two doors, told apart by nginx (the only thing that can reach this server,
which listens on loopback):

- "lab": https://10.10.10.70:8447, which nginx serves only to the student's
  own lab session.  Whoever is there is already signed in to the lab, so
  there is no second login.
- "remote": https://<machine>:8446/control/, from the student's own computer
  on their private network.  That needs the lab login: user student and the
  current lab password.  A session ends when the password changes (every new
  lab session), after 12 hours, or at sign out.  Five wrong passwords from one
  address lock it out for five minutes.

nginx sets the X-HR-Door header itself on each door and overwrites anything a
browser sent, so a request cannot claim the trusted door.

Author: Tim Rice
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from . import labinfo

SESSION_HOURS = 12
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300

_sessions: dict[str, tuple[float, str]] = {}   # token -> (expires, password fingerprint)
_failures: dict[str, list[float]] = {}         # client address -> failure times
_lock = threading.Lock()


def _fingerprint(password: str) -> str:
    return hashlib.sha256(("hackrange-control:" + password).encode()).hexdigest()


def locked_out(client: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(client, []) if now - t < LOCKOUT_SECONDS]
        _failures[client] = recent
        return len(recent) >= MAX_FAILURES


def login(client: str, username: str, password: str) -> str | None:
    """A session token for the right login, or None."""
    if locked_out(client):
        return None
    current = labinfo.access_password()
    ok = bool(current) and hmac.compare_digest(username, "student") & hmac.compare_digest(password, current)
    if not ok:
        with _lock:
            _failures.setdefault(client, []).append(time.time())
        return None
    token = secrets.token_urlsafe(32)
    with _lock:
        _failures.pop(client, None)
        _sessions[token] = (time.time() + SESSION_HOURS * 3600, _fingerprint(current))
    return token


def logout(token: str) -> None:
    with _lock:
        _sessions.pop(token, None)


def valid(token: str) -> bool:
    if not token:
        return False
    with _lock:
        entry = _sessions.get(token)
    if not entry:
        return False
    expires, fp = entry
    if time.time() > expires or fp != _fingerprint(labinfo.access_password()):
        logout(token)
        return False
    return True
