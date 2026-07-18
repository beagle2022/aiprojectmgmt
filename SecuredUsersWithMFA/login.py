"""
login.py — MFA login CLI

Usage:
    python login.py              # interactive login, then launches copilot
    python login.py --add-user   # add a new user to the system
    python login.py --list-users # list all registered users
    python login.py --logout     # revoke your session token

Three-step login flow:
    Step 1 — Email + password
    Step 2 — Email OTP (6-digit code sent to registered email)
    Step 3 — SMS OTP  (6-digit code sent to registered phone)

After passing all three steps, a signed session token is written to
data/.session and the copilot starts automatically.
"""

import argparse
import asyncio
import getpass
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
load_dotenv()

from auth.users import (
    create_user, list_users, deactivate_user,
    verify_credentials, generate_otp, verify_otp,
    send_email_otp, send_sms_otp, record_login,
)
from auth.session import (
    create_session, validate_session,
    revoke_session, revoke_all_user_sessions,
)

SESSION_TOKEN_FILE = os.path.join(_ROOT, "data", ".session")


# ── Display helpers ───────────────────────────────────────────────────────────

def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _banner():
    print("\n╔══════════════════════════════════════════╗")
    print("║      AI Project Management Copilot       ║")
    print("║            Secure Login Portal            ║")
    print("╚══════════════════════════════════════════╝\n")


def _step(n: int, label: str, done: bool = False):
    icon = "✓" if done else "→"
    colour = "\033[32m" if done else "\033[36m"
    reset = "\033[0m"
    print(f"  {colour}{icon} Step {n}: {label}{reset}")


def _err(msg: str):
    print(f"\n  \033[31m✗ {msg}\033[0m\n")


def _ok(msg: str):
    print(f"\n  \033[32m✓ {msg}\033[0m\n")


def _ask_otp(prompt: str, max_tries: int = 3) -> str:
    for attempt in range(1, max_tries + 1):
        code = input(f"  {prompt} (attempt {attempt}/{max_tries}): ").strip()
        if code:
            return code
    return ""


# ── Session persistence ───────────────────────────────────────────────────────

def _save_session_token(token: str) -> None:
    os.makedirs(os.path.dirname(SESSION_TOKEN_FILE), exist_ok=True)
    with open(SESSION_TOKEN_FILE, "w") as f:
        f.write(token)


def _load_session_token() -> str:
    if not os.path.exists(SESSION_TOKEN_FILE):
        return ""
    with open(SESSION_TOKEN_FILE) as f:
        return f.read().strip()


def _clear_session_token() -> None:
    if os.path.exists(SESSION_TOKEN_FILE):
        os.remove(SESSION_TOKEN_FILE)


# ── Login flow ────────────────────────────────────────────────────────────────

def login() -> dict | None:
    """
    Run the full 3-step MFA login flow.
    Returns the authenticated user dict on success, None on failure.
    """
    _clear()
    _banner()

    # ── Check for an existing valid session ──
    existing_token = _load_session_token()
    if existing_token:
        session = validate_session(existing_token)
        if session:
            _ok(f"Welcome back, {session['name']} ({session['role']})")
            print(f"  Session active until: {session['expiry'][:19].replace('T',' ')} UTC")
            print()
            choice = input("  Continue with existing session? [Y/n] › ").strip().lower()
            if choice in ("", "y", "yes"):
                return session
            else:
                revoke_session(existing_token)
                _clear_session_token()
                _clear()
                _banner()

    print("  Please verify your identity in three steps.\n")
    _step(1, "Email + password")
    _step(2, "Email verification code")
    _step(3, "SMS verification code")
    print()

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1 — Email + password
    # ──────────────────────────────────────────────────────────────────────────
    print("─" * 46)
    print("  Step 1 of 3 — Email and password\n")

    for attempt in range(1, 4):
        email    = input("  Email    › ").strip().lower()
        password = getpass.getpass("  Password › ")

        user = verify_credentials(email, password)
        if user:
            break
        _err(f"Invalid email or password. ({attempt}/3)")
        if attempt == 3:
            _err("Too many failed attempts. Please try again later.")
            return None

    _ok(f"Credentials verified for {user['name']}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2 — Email OTP
    # ──────────────────────────────────────────────────────────────────────────
    print("─" * 46)
    print("  Step 2 of 3 — Email verification\n")

    email_otp = generate_otp(email, "email")
    send_email_otp(email, email_otp, user["name"])
    print(f"  A 6-digit code has been sent to {email}")
    print(f"  (Code expires in 5 minutes)\n")

    for attempt in range(1, 4):
        code = input(f"  Enter email code (attempt {attempt}/3) › ").strip()
        ok, msg = verify_otp(email, "email", code)
        if ok:
            break
        _err(msg)
        if attempt == 3:
            _err("Email verification failed. Please restart login.")
            return None

    _ok("Email verified")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3 — SMS OTP
    # ──────────────────────────────────────────────────────────────────────────
    print("─" * 46)
    print("  Step 3 of 3 — Phone verification\n")

    phone = user["phone"]
    masked_phone = phone[:3] + "****" + phone[-3:]
    sms_otp = generate_otp(email, "sms")
    send_sms_otp(phone, sms_otp)
    print(f"  A 6-digit code has been sent to {masked_phone}")
    print(f"  (Code expires in 5 minutes)\n")

    for attempt in range(1, 4):
        code = input(f"  Enter SMS code (attempt {attempt}/3) › ").strip()
        ok, msg = verify_otp(email, "sms", code)
        if ok:
            break
        _err(msg)
        if attempt == 3:
            _err("Phone verification failed. Please restart login.")
            return None

    _ok("Phone verified")

    # ──────────────────────────────────────────────────────────────────────────
    # All steps passed — create session
    # ──────────────────────────────────────────────────────────────────────────
    token = create_session(email, user["name"], user["role"])
    _save_session_token(token)
    record_login(email)

    print("─" * 46)
    _ok(f"Access granted — welcome, {user['name']} ({user['role']})")
    print(f"  Session valid for 8 hours.\n")

    return {"email": email, "name": user["name"], "role": user["role"], "token": token}


# ── Admin helpers ─────────────────────────────────────────────────────────────

def add_user_interactive():
    _banner()
    print("  Add a new user\n")
    name     = input("  Full name      › ").strip()
    email    = input("  Email          › ").strip().lower()
    phone    = input("  Phone (+CC...) › ").strip()
    role     = input("  Role           › [developer] ").strip() or "developer"
    password = getpass.getpass("  Password       › ")
    confirm  = getpass.getpass("  Confirm pass   › ")

    if password != confirm:
        _err("Passwords do not match.")
        return

    try:
        create_user(email=email, phone=phone, name=name,
                    password=password, role=role)
        _ok(f"User {email} created successfully.")
    except ValueError as e:
        _err(str(e))


def list_users_table():
    users = list_users()
    if not users:
        print("  No users registered yet. Run with --add-user.\n")
        return
    print(f"\n  {'Name':<20} {'Email':<28} {'Role':<18} {'Active':<8} {'Last login'}")
    print("  " + "─" * 86)
    for u in users:
        last = (u.get("last_login") or "Never")[:16].replace("T", " ")
        active = "Yes" if u.get("active") else "No"
        print(f"  {u['name']:<20} {u['email']:<28} {u['role']:<18} {active:<8} {last}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def _run_copilot(user: dict):
    """Launch the copilot after successful login."""
    from copilot.config import Config
    from copilot.memory import MemoryManager
    from copilot.orchestrator import Orchestrator

    config = Config()
    missing = config.validate()
    if missing:
        print(f"[Error] Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    memory       = MemoryManager(config)
    orchestrator = Orchestrator(config, memory)

    print("╔══════════════════════════════════════════╗")
    print("║      AI Project Management Copilot       ║")
    print(f"║  Logged in as: {user['name'][:24]:<24}  ║")
    print("╚══════════════════════════════════════════╝")
    print("Commands: 'memory' — inspect LTM | 'logout' — sign out | 'exit' — quit\n")

    while True:
        try:
            user_input = input("You › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("Goodbye.")
            break
        if user_input.lower() == "logout":
            token = _load_session_token()
            if token:
                revoke_session(token)
                _clear_session_token()
            _ok("Logged out. Session revoked.")
            break
        if user_input.lower() == "memory":
            memory.dump()
            continue

        response = await orchestrator.run(user_input)
        print(f"\nCopilot › {response}\n")


def main():
    parser = argparse.ArgumentParser(description="AI PM Copilot — Secure login")
    parser.add_argument("--add-user",   action="store_true", help="Register a new user")
    parser.add_argument("--list-users", action="store_true", help="List all users")
    parser.add_argument("--deactivate", metavar="EMAIL",     help="Deactivate a user")
    parser.add_argument("--logout",     action="store_true", help="Revoke current session")
    args = parser.parse_args()

    if args.add_user:
        add_user_interactive()
        return

    if args.list_users:
        list_users_table()
        return

    if args.deactivate:
        if deactivate_user(args.deactivate):
            revoke_all_user_sessions(args.deactivate)
            _ok(f"User {args.deactivate} deactivated and sessions revoked.")
        else:
            _err(f"User {args.deactivate} not found.")
        return

    if args.logout:
        token = _load_session_token()
        if token:
            revoke_session(token)
            _clear_session_token()
            _ok("Logged out successfully.")
        else:
            print("No active session found.")
        return

    # Run login flow
    user = login()
    if not user:
        print("Login failed. Exiting.")
        sys.exit(1)

    # Launch copilot
    asyncio.run(_run_copilot(user))


if __name__ == "__main__":
    main()
