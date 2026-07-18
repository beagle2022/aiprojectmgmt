"""
guardrails.py — Cybersecurity guardrails for the AI PM Copilot

Covers:
  1. Human-in-the-loop (HITL) approval gate
  2. PII detection and redaction
  3. Input sanitisation (prompt injection defence)
  4. Output validation
  5. Rate limiting
  6. Audit logging
"""

from __future__ import annotations

import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import hashlib
import os
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    filename="data/audit.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
audit_log = logging.getLogger("copilot.audit")


# ══════════════════════════════════════════════════════════════════════════════
# 1. HUMAN-IN-THE-LOOP GATE
# ══════════════════════════════════════════════════════════════════════════════

# Actions that require explicit human approval before execution.
# Add any action that is irreversible or has external side-effects.
HITL_REQUIRED_ACTIONS = {
    "post_slack_message":    "Post a message to Slack",
    "create_jira_ticket":    "Create a new Jira ticket",
    "update_jira_ticket":    "Update an existing Jira ticket",
    "close_jira_ticket":     "Close / resolve a Jira ticket",
    "merge_pull_request":    "Merge a GitHub pull request",
    "trigger_deployment":    "Trigger a CI/CD deployment pipeline",
    "delete_memory":         "Delete entries from long-term memory",
    "send_email":            "Send an email on behalf of a team member",
}


def require_human_approval(action_key: str, description: str, payload: dict) -> bool:
    """
    Prompt the human operator for explicit approval before executing
    a sensitive action. Returns True if approved, False if rejected.

    Usage:
        if not require_human_approval("post_slack_message", "Post standup digest", data):
            return "[Action cancelled by user]"
    """
    print("\n" + "─" * 60)
    print("⚠  HUMAN APPROVAL REQUIRED")
    print("─" * 60)
    print(f"Action  : {HITL_REQUIRED_ACTIONS.get(action_key, action_key)}")
    print(f"Details : {description}")
    print(f"Payload preview:\n{json.dumps(payload, indent=2)[:400]}")
    print("─" * 60)

    for _ in range(3):
        response = input("Approve? [yes/no] › ").strip().lower()
        if response in ("yes", "y"):
            audit_log.info(f"HITL_APPROVED | action={action_key} | details={description}")
            print("✓ Approved.\n")
            return True
        if response in ("no", "n"):
            audit_log.warning(f"HITL_REJECTED | action={action_key} | details={description}")
            print("✗ Rejected. Action cancelled.\n")
            return False
        print("Please type 'yes' or 'no'.")

    # Default deny after 3 invalid attempts
    audit_log.warning(f"HITL_TIMEOUT | action={action_key} | defaulting to deny")
    print("✗ No valid response — action cancelled.\n")
    return False


def hitl_gate(action_key: str):
    """
    Decorator that wraps any tool method with a HITL approval gate.

    Usage:
        @hitl_gate("post_slack_message")
        def post_slack_message(self, text, channel=None):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            payload = {"args": str(args[1:]), "kwargs": str(kwargs)}
            description = f"Calling {fn.__name__}"
            if not require_human_approval(action_key, description, payload):
                return False
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# 2. PII DETECTION AND REDACTION
# ══════════════════════════════════════════════════════════════════════════════

# Regex patterns for common PII types
PII_PATTERNS: dict[str, re.Pattern] = {
    "email":          re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone_us":       re.compile(r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "phone_in":       re.compile(r"\b(\+91[-.\s]?)?[6-9]\d{9}\b"),
    "credit_card":    re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "ssn":            re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "ip_address":     re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "api_key_generic":re.compile(r"\b(sk-[A-Za-z0-9\-_]{20,}|ghp_[A-Za-z0-9]{36}|xoxb-[A-Za-z0-9\-]+)\b"),
    "jwt":            re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    "password_field": re.compile(r"(?i)(password|passwd|secret|token)\s*[:=]\s*\S+"),
}

REDACTION_LABEL = {
    "email":           "[EMAIL REDACTED]",
    "phone_us":        "[PHONE REDACTED]",
    "phone_in":        "[PHONE REDACTED]",
    "credit_card":     "[CARD REDACTED]",
    "ssn":             "[SSN REDACTED]",
    "ip_address":      "[IP REDACTED]",
    "api_key_generic": "[API KEY REDACTED]",
    "jwt":             "[TOKEN REDACTED]",
    "password_field":  "[CREDENTIAL REDACTED]",
}


@dataclass
class PIIResult:
    redacted_text: str
    findings: list[dict]           # [{type, original_hash, position}]
    has_pii: bool


def detect_and_redact_pii(text: str, redact: bool = True) -> PIIResult:
    """
    Scan text for PII. If redact=True, replace matches with labels.
    Originals are hashed (not stored) so they can be verified without re-exposure.

    Usage:
        result = detect_and_redact_pii(user_input)
        if result.has_pii:
            print(f"Found PII: {result.findings}")
        safe_text = result.redacted_text
    """
    findings = []
    result_text = text

    for pii_type, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(result_text):
            original = match.group()
            findings.append({
                "type": pii_type,
                "original_hash": hashlib.sha256(original.encode()).hexdigest()[:16],
                "position": match.start(),
            })

    if redact:
        for pii_type, pattern in PII_PATTERNS.items():
            result_text = pattern.sub(REDACTION_LABEL[pii_type], result_text)

    if findings:
        audit_log.warning(
            f"PII_DETECTED | types={[f['type'] for f in findings]} | count={len(findings)}"
        )

    return PIIResult(
        redacted_text=result_text,
        findings=findings,
        has_pii=len(findings) > 0,
    )


def pii_guard(text: str) -> str:
    """
    Convenience wrapper — redacts PII and returns the safe string.
    Logs a warning if PII was found.

    Usage:
        safe_input = pii_guard(user_message)
    """
    result = detect_and_redact_pii(text)
    if result.has_pii:
        print(f"  [Security] PII detected and redacted: "
              f"{[f['type'] for f in result.findings]}")
    return result.redacted_text


# ══════════════════════════════════════════════════════════════════════════════
# 3. INPUT SANITISATION (PROMPT INJECTION DEFENCE)
# ══════════════════════════════════════════════════════════════════════════════

# Phrases that are always safe regardless of pattern matches
# Add any legitimate development or task phrases here
INJECTION_WHITELIST = [
    re.compile(r"develop|dashboard|skill|claude|sonnet|integration|build|create|design", re.I),
    re.compile(r"how to|help me|can you|please|generate|write|update|improve", re.I),
    re.compile(r"sprint|backlog|standup|ticket|story|task|review|risk|deploy", re.I),
    re.compile(r"act as (a )?(pm|product manager|scrum master|developer|engineer)", re.I),
    re.compile(r"you are (a )?(pm|product manager|scrum master|developer|engineer|assistant)", re.I),
]

# Patterns that attempt to hijack the agent's system prompt or persona
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?!the copilot|a pm|a product|a scrum|a developer|an engineer)", re.I),
    re.compile(r"(forget|disregard|override)\s+(your\s+)?(instructions|prompt|rules)", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"<\s*(script|iframe|object|embed)\s*>", re.I),
    re.compile(r"system\s*:\s*(you are|ignore)", re.I),
    re.compile(r"print\s+(the\s+)?(system\s+prompt|api\s+key)", re.I),
]

# Maximum safe input length
MAX_INPUT_LENGTH = 12000


def sanitise_input(text: str) -> tuple[str, list[str]]:
    """
    Check user input for prompt injection attempts and enforce length limits.
    Returns (sanitised_text, list_of_warnings).

    Whitelist takes priority — if any whitelist pattern matches, injection
    patterns are skipped entirely. This prevents legitimate development
    prompts (e.g. dashboard building, Claude skill development) from
    being blocked.

    Usage:
        clean, warnings = sanitise_input(user_message)
        if warnings:
            print("Suspicious input detected")
    """
    warnings = []

    # Length check
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]
        warnings.append(f"Input truncated to {MAX_INPUT_LENGTH} characters")

    # Whitelist check — if any safe pattern matches, skip injection scan
    is_whitelisted = any(p.search(text) for p in INJECTION_WHITELIST)
    if is_whitelisted:
        return text, warnings

    # Injection pattern check (only runs if not whitelisted)
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            warnings.append(f"Potential prompt injection detected: {pattern.pattern[:40]}")
            audit_log.warning(
                f"INJECTION_ATTEMPT | pattern={pattern.pattern[:40]} | "
                f"input_hash={hashlib.sha256(text.encode()).hexdigest()[:16]}"
            )

    return text, warnings


# ══════════════════════════════════════════════════════════════════════════════
# 4. OUTPUT VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

# Strings that should never appear in agent output
OUTPUT_BLOCKLIST = [
    r"ANTHROPIC_API_KEY",
    r"sk-ant-[A-Za-z0-9\-_]+",
    r"ghp_[A-Za-z0-9]+",
    r"xoxb-[A-Za-z0-9\-]+",
    r"(?i)my (system )?prompt is",
    r"(?i)my instructions (are|say)",
]


def validate_output(text: str) -> tuple[str, bool]:
    """
    Scan agent output for secrets or forbidden content before
    delivering to the user. Returns (safe_text, was_modified).

    Usage:
        safe_response, modified = validate_output(agent_response)
    """
    modified = False
    result = text

    for pattern_str in OUTPUT_BLOCKLIST:
        pattern = re.compile(pattern_str)
        if pattern.search(result):
            result = pattern.sub("[REDACTED BY OUTPUT VALIDATOR]", result)
            modified = True
            audit_log.error(
                f"OUTPUT_LEAK_BLOCKED | pattern={pattern_str[:40]}"
            )

    return result, modified


# ══════════════════════════════════════════════════════════════════════════════
# 5. RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RateLimiter:
    """
    Simple token-bucket rate limiter.
    Prevents runaway agent loops or abuse from burning API credits.

    Usage:
        limiter = RateLimiter(max_calls=20, window_seconds=60)

        if not limiter.allow():
            print("Rate limit reached — please wait.")
        else:
            # proceed with API call
    """
    max_calls: int = 20               # max calls per window
    window_seconds: int = 60          # rolling window in seconds
    _calls: list[float] = field(default_factory=list)

    def allow(self) -> bool:
        now = time.time()
        # Drop calls outside the window
        self._calls = [t for t in self._calls if now - t < self.window_seconds]
        if len(self._calls) >= self.max_calls:
            audit_log.warning(
                f"RATE_LIMIT_HIT | calls={len(self._calls)} | window={self.window_seconds}s"
            )
            return False
        self._calls.append(now)
        return True

    def status(self) -> str:
        now = time.time()
        recent = [t for t in self._calls if now - t < self.window_seconds]
        return f"{len(recent)}/{self.max_calls} calls in last {self.window_seconds}s"


# ══════════════════════════════════════════════════════════════════════════════
# 6. AUDIT LOGGER
# ══════════════════════════════════════════════════════════════════════════════

class AuditLogger:
    """
    Structured audit logger for all agent actions.
    Writes to data/audit.log in JSON-lines format.

    Usage:
        logger = AuditLogger()
        logger.log_request("user_message", "plan the sprint")
        logger.log_agent_call("sprint_planner", "claude-sonnet-4-6", 512)
        logger.log_tool_call("fetch_jira_tickets", success=True)
    """

    def __init__(self, log_path: str = "data/audit.log"):
        os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else ".", exist_ok=True)
        self._path = log_path

    def _write(self, record: dict) -> None:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def log_request(self, source: str, content_hash: str) -> None:
        self._write({"event": "REQUEST", "source": source, "content_hash": content_hash})

    def log_agent_call(self, agent: str, model: str, tokens_used: int) -> None:
        self._write({"event": "AGENT_CALL", "agent": agent, "model": model, "tokens": tokens_used})

    def log_tool_call(self, tool: str, success: bool, error: str = "") -> None:
        self._write({"event": "TOOL_CALL", "tool": tool, "success": success, "error": error})

    def log_hitl(self, action: str, approved: bool) -> None:
        self._write({"event": "HITL", "action": action, "approved": approved})

    def log_security_event(self, event_type: str, detail: str) -> None:
        self._write({"event": f"SECURITY_{event_type}", "detail": detail})


# ══════════════════════════════════════════════════════════════════════════════
# 7. MASTER SECURITY PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SecurityPipeline:
    """
    Single entry point that runs all guardrails on every user message.

    Usage (in orchestrator.py):

        from copilot.guardrails import SecurityPipeline
        security = SecurityPipeline()

        # In Orchestrator.__init__:
        self.security = SecurityPipeline()

        # In Orchestrator.run():
        user_message, blocked = self.security.process_input(user_message)
        if blocked:
            return "Your message was blocked by the security pipeline."

        # Before returning response:
        response = self.security.process_output(response)
    """

    rate_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(max_calls=30, window_seconds=60))
    audit: AuditLogger = field(default_factory=AuditLogger)
    block_on_injection: bool = True

    def process_input(self, text: str) -> tuple[str, bool]:
        """
        Run full input pipeline. Returns (processed_text, is_blocked).
        is_blocked=True means the message should NOT be sent to the LLM.
        """
        # 1. Rate limit check
        if not self.rate_limiter.allow():
            self.audit.log_security_event("RATE_LIMIT", self.rate_limiter.status())
            print(f"  [Security] Rate limit reached. {self.rate_limiter.status()}")
            return text, True

        # 2. Input sanitisation / injection check
        text, warnings = sanitise_input(text)
        if warnings:
            for w in warnings:
                print(f"  [Security] {w}")
            if self.block_on_injection:
                self.audit.log_security_event("INJECTION_BLOCKED", str(warnings))
                return text, True

        # 3. PII redaction
        text = pii_guard(text)

        # 4. Audit the incoming request
        self.audit.log_request(
            source="user",
            content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
        )

        return text, False

    def process_output(self, text: str) -> str:
        """
        Run full output pipeline. Redacts any leaked secrets.
        """
        text, modified = validate_output(text)
        if modified:
            print("  [Security] Output contained sensitive data — redacted before delivery.")
        return text
