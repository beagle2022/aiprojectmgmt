"""
auth/users.py — User database and authentication management

Stores users in data/users.json. Each user record:
{
  "email": "alice@company.com",
  "phone": "+919876543210",
  "name": "Alice Chen",
  "role": "backend_engineer",
  "password_hash": "<bcrypt hash>",
  "mfa_enabled": true,
  "active": true,
  "created_at": "2026-07-01T10:00:00Z",
  "last_login": "2026-07-18T09:00:00Z"
}

MFA OTP codes are stored in data/otp_store.json with a 5-minute TTL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import string
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

USERS_FILE = os.path.join(_ROOT, "data", "users.json")
OTP_FILE   = os.path.join(_ROOT, "data", "otp_store.json")
OTP_TTL_MINUTES = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str = "") -> str:
    """SHA-256 password hash with salt. Use bcrypt in production."""
    if not salt:
        salt = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split(":", 1)
        return hmac.compare_digest(_hash_password(password, salt), stored_hash)
    except Exception:
        return False


def _load_users() -> dict:
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def _save_users(users: dict) -> None:
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _load_otps() -> dict:
    os.makedirs(os.path.dirname(OTP_FILE), exist_ok=True)
    if not os.path.exists(OTP_FILE):
        return {}
    with open(OTP_FILE) as f:
        return json.load(f)


def _save_otps(otps: dict) -> None:
    os.makedirs(os.path.dirname(OTP_FILE), exist_ok=True)
    with open(OTP_FILE, "w") as f:
        json.dump(otps, f, indent=2)


# ── User management ───────────────────────────────────────────────────────────

def create_user(email: str, phone: str, name: str, password: str,
                role: str = "developer") -> dict:
    """
    Create a new user. Phone must include country code e.g. +919876543210.
    Returns the user record (without password hash).
    """
    users = _load_users()
    email = email.strip().lower()
    if email in users:
        raise ValueError(f"User {email} already exists.")

    record = {
        "email":         email,
        "phone":         phone.strip(),
        "name":          name.strip(),
        "role":          role,
        "password_hash": _hash_password(password),
        "mfa_enabled":   True,
        "active":        True,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "last_login":    None,
        "login_count":   0,
    }
    users[email] = record
    _save_users(users)
    safe = {k: v for k, v in record.items() if k != "password_hash"}
    print(f"[Auth] User created: {email} ({role})")
    return safe


def get_user(email: str) -> dict | None:
    users = _load_users()
    return users.get(email.strip().lower())


def list_users() -> list[dict]:
    users = _load_users()
    return [
        {k: v for k, v in u.items() if k != "password_hash"}
        for u in users.values()
    ]


def deactivate_user(email: str) -> bool:
    users = _load_users()
    email = email.strip().lower()
    if email not in users:
        return False
    users[email]["active"] = False
    _save_users(users)
    return True


def verify_credentials(email: str, password: str) -> dict | None:
    """
    Step 1 of login: verify email + password.
    Returns user record if correct, None if not.
    """
    user = get_user(email)
    if not user:
        return None
    if not user.get("active"):
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return user


# ── OTP management ────────────────────────────────────────────────────────────

def generate_otp(email: str, channel: str) -> str:
    """
    Generate a 6-digit OTP for the given email and channel ('email' or 'sms').
    Stores it with a TTL. Returns the OTP code.
    """
    code = "".join(random.choices(string.digits, k=6))
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()

    otps = _load_otps()
    key = f"{email}:{channel}"
    otps[key] = {"code": code, "expiry": expiry, "attempts": 0}
    _save_otps(otps)
    return code


def verify_otp(email: str, channel: str, code: str) -> tuple[bool, str]:
    """
    Verify a submitted OTP code.
    Returns (success, message).
    Max 3 attempts per OTP before it is invalidated.
    """
    otps = _load_otps()
    key = f"{email}:{channel}"
    entry = otps.get(key)

    if not entry:
        return False, "No OTP found. Please request a new code."

    # Expiry check
    expiry = datetime.fromisoformat(entry["expiry"])
    if datetime.now(timezone.utc) > expiry:
        del otps[key]
        _save_otps(otps)
        return False, f"OTP expired. Please request a new code."

    # Attempt limit
    entry["attempts"] += 1
    if entry["attempts"] > 3:
        del otps[key]
        _save_otps(otps)
        return False, "Too many failed attempts. Please request a new code."

    # Code check
    if not hmac.compare_digest(entry["code"], code.strip()):
        _save_otps(otps)
        remaining = 3 - entry["attempts"]
        return False, f"Incorrect code. {remaining} attempt(s) remaining."

    # Success — delete OTP
    del otps[key]
    _save_otps(otps)
    return True, "Verified."


def record_login(email: str) -> None:
    users = _load_users()
    email = email.strip().lower()
    if email in users:
        users[email]["last_login"] = datetime.now(timezone.utc).isoformat()
        users[email]["login_count"] = users[email].get("login_count", 0) + 1
        _save_users(users)


# ── OTP delivery (console + optional Twilio/SendGrid) ─────────────────────────

def send_email_otp(email: str, otp: str, user_name: str = "") -> bool:
    """
    Send OTP via email. Uses SendGrid if SENDGRID_API_KEY is set.
    Falls back to console print for development.
    """
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@aipmcopilot.dev")

    if api_key:
        try:
            import requests
            payload = {
                "personalizations": [{"to": [{"email": email}]}],
                "from": {"email": from_email},
                "subject": "AI PM Copilot — Your login code",
                "content": [{
                    "type": "text/plain",
                    "value": (
                        f"Hi {user_name or email},\n\n"
                        f"Your login verification code is: {otp}\n\n"
                        f"This code expires in {OTP_TTL_MINUTES} minutes.\n"
                        f"Do not share this code with anyone.\n\n"
                        f"AI PM Copilot"
                    )
                }]
            }
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json=payload, timeout=10,
            )
            if resp.status_code == 202:
                print(f"[Auth] Email OTP sent to {email}")
                return True
            else:
                print(f"[Auth] SendGrid error: {resp.status_code} {resp.text[:80]}")
        except Exception as e:
            print(f"[Auth] Email send failed: {e}")

    # Development fallback — print to console
    print(f"\n{'='*50}")
    print(f"  [DEV] EMAIL OTP for {email}")
    print(f"  Code: {otp}  (expires in {OTP_TTL_MINUTES} min)")
    print(f"{'='*50}\n")
    return True


def send_sms_otp(phone: str, otp: str) -> bool:
    """
    Send OTP via SMS. Uses Twilio if TWILIO_* env vars are set.
    Falls back to console print for development.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")

    if account_sid and auth_token and from_number:
        try:
            import requests
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={
                    "From": from_number,
                    "To": phone,
                    "Body": f"AI PM Copilot login code: {otp}. Expires in {OTP_TTL_MINUTES} min. Do not share.",
                },
                timeout=10,
            )
            if resp.status_code in (200, 201):
                print(f"[Auth] SMS OTP sent to {phone}")
                return True
            else:
                print(f"[Auth] Twilio error: {resp.status_code} {resp.text[:80]}")
        except Exception as e:
            print(f"[Auth] SMS send failed: {e}")

    # Development fallback
    print(f"\n{'='*50}")
    print(f"  [DEV] SMS OTP for {phone}")
    print(f"  Code: {otp}  (expires in {OTP_TTL_MINUTES} min)")
    print(f"{'='*50}\n")
    return True
