"""
auth/session.py — Session token management

After successful MFA, issues a signed session token stored in
data/sessions.json with a configurable TTL (default 8 hours).
The orchestrator checks this token on every call.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

SESSIONS_FILE  = os.path.join(_ROOT, "data", "sessions.json")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production-use-a-long-random-string")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))


def _load_sessions() -> dict:
    os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
    if not os.path.exists(SESSIONS_FILE):
        return {}
    with open(SESSIONS_FILE) as f:
        return json.load(f)


def _save_sessions(sessions: dict) -> None:
    os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)


def _sign(token: str) -> str:
    return hashlib.sha256(f"{SESSION_SECRET}{token}".encode()).hexdigest()[:16]


def create_session(email: str, name: str, role: str) -> str:
    """
    Create a new session after successful MFA.
    Returns a session token string.
    """
    raw = secrets.token_urlsafe(32)
    token = f"{raw}.{_sign(raw)}"
    expiry = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()

    sessions = _load_sessions()
    sessions[token] = {
        "email":      email,
        "name":       name,
        "role":       role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expiry":     expiry,
    }
    _save_sessions(sessions)
    return token


def validate_session(token: str) -> dict | None:
    """
    Validate a session token. Returns session data if valid, None if not.
    """
    if not token:
        return None

    # Signature check
    parts = token.rsplit(".", 1)
    if len(parts) != 2 or parts[1] != _sign(parts[0]):
        return None

    sessions = _load_sessions()
    session = sessions.get(token)
    if not session:
        return None

    # Expiry check
    expiry = datetime.fromisoformat(session["expiry"])
    if datetime.now(timezone.utc) > expiry:
        del sessions[token]
        _save_sessions(sessions)
        return None

    return session


def revoke_session(token: str) -> None:
    """Revoke (logout) a session."""
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)


def revoke_all_user_sessions(email: str) -> int:
    """Revoke all sessions for a given user. Returns count revoked."""
    sessions = _load_sessions()
    to_remove = [t for t, s in sessions.items() if s["email"] == email]
    for t in to_remove:
        del sessions[t]
    _save_sessions(sessions)
    return len(to_remove)


def active_sessions() -> list[dict]:
    """List all active (non-expired) sessions."""
    sessions = _load_sessions()
    now = datetime.now(timezone.utc)
    result = []
    for token, s in sessions.items():
        expiry = datetime.fromisoformat(s["expiry"])
        if now <= expiry:
            result.append({**s, "token_prefix": token[:8] + "..."})
    return result
