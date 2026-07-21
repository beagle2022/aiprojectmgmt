"""
copilot/token_tracker.py — Token usage tracking and cost estimation

Captures input/output token counts from every Anthropic API call,
persists them to data/token_usage.json, and provides reporting.

USAGE:
    from copilot.token_tracker import TokenTracker
    tracker = TokenTracker()

    # Record a call
    tracker.record(
        agent="orchestrator",
        model="claude-sonnet-4-6",
        input_tokens=850,
        output_tokens=312,
    )

    # Print a report
    tracker.report()

    # Get totals
    totals = tracker.totals()
    print(totals["total_cost_usd"])
"""

from __future__ import annotations

import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
import os
from datetime import datetime, timezone
from typing import Any


# ── Pricing table (USD per million tokens, July 2026) ─────────────────────────
# Update these when Anthropic changes pricing.
# Source: https://www.anthropic.com/pricing
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {
        "input_per_1m":  15.00,
        "output_per_1m": 75.00,
    },
    "claude-sonnet-4-6": {
        "input_per_1m":   3.00,
        "output_per_1m": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_1m":  0.80,
        "output_per_1m": 4.00,
    },
    # Fallback for unknown models
    "_default": {
        "input_per_1m":  3.00,
        "output_per_1m": 15.00,
    },
}

USAGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "token_usage.json"
)


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["_default"])
    input_cost  = (input_tokens  / 1_000_000) * pricing["input_per_1m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_1m"]
    return round(input_cost + output_cost, 6)


# ── TokenTracker ──────────────────────────────────────────────────────────────

class TokenTracker:
    """
    Records token usage for every LLM call and persists it to disk.
    Provides session totals, per-agent breakdown, and cost estimates.
    """

    def __init__(self, usage_file: str = USAGE_FILE):
        self._file = usage_file
        self._session: list[dict] = []          # in-memory log for this session
        os.makedirs(os.path.dirname(self._file) if os.path.dirname(self._file) else ".", exist_ok=True)

    # ── Record a single API call ───────────────────────────────────────────

    def record(
        self,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_email: str = "unknown",
    ) -> dict:
        """
        Record one API call. Returns the usage record.

        Args:
            agent:         Name of the agent or component that made the call
                           e.g. 'orchestrator', 'sprint_planner', 'code_reviewer'
            model:         Exact model string e.g. 'claude-sonnet-4-6'
            input_tokens:  From response.usage.input_tokens
            output_tokens: From response.usage.output_tokens
            user_email:    Who triggered this call (from active session)
        """
        cost = _cost_usd(model, input_tokens, output_tokens)
        record = {
            "ts":            datetime.now(timezone.utc).isoformat(),
            "agent":         agent,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "cost_usd":      cost,
            "user":          user_email,
        }
        self._session.append(record)
        self._append_to_file(record)
        return record

    # ── Session aggregates ─────────────────────────────────────────────────

    def session_totals(self) -> dict:
        """Totals for the current session (since this object was created)."""
        return self._aggregate(self._session)

    def totals(self) -> dict:
        """Totals across all recorded sessions (from disk)."""
        return self._aggregate(self._load_all())

    def by_agent(self, records: list[dict] | None = None) -> dict[str, dict]:
        """Break down token usage per agent."""
        if records is None:
            records = self._load_all()
        agents: dict[str, list] = {}
        for r in records:
            agents.setdefault(r["agent"], []).append(r)
        return {agent: self._aggregate(recs) for agent, recs in agents.items()}

    def by_model(self, records: list[dict] | None = None) -> dict[str, dict]:
        """Break down token usage per model."""
        if records is None:
            records = self._load_all()
        models: dict[str, list] = {}
        for r in records:
            models.setdefault(r["model"], []).append(r)
        return {model: self._aggregate(recs) for model, recs in models.items()}

    def by_user(self, records: list[dict] | None = None) -> dict[str, dict]:
        """Break down token usage per logged-in user."""
        if records is None:
            records = self._load_all()
        users: dict[str, list] = {}
        for r in records:
            users.setdefault(r["user"], []).append(r)
        return {user: self._aggregate(recs) for user, recs in users.items()}

    def recent(self, n: int = 10) -> list[dict]:
        """Return the n most recent calls."""
        return self._load_all()[-n:]

    # ── Reports ────────────────────────────────────────────────────────────

    def report(self, scope: str = "all") -> None:
        """
        Print a formatted token usage report to the terminal.

        Args:
            scope: 'session' for current session only, 'all' for lifetime totals
        """
        records = self._session if scope == "session" else self._load_all()
        totals  = self._aggregate(records)
        agents  = self.by_agent(records)
        models  = self.by_model(records)

        print("\n" + "═" * 58)
        print(f"  Token Usage Report  ({scope})")
        print("═" * 58)
        print(f"  Total calls    : {totals['calls']:,}")
        print(f"  Input tokens   : {totals['input_tokens']:,}")
        print(f"  Output tokens  : {totals['output_tokens']:,}")
        print(f"  Total tokens   : {totals['total_tokens']:,}")
        print(f"  Estimated cost : ${totals['cost_usd']:.4f} USD")
        print()

        print("  By agent:")
        for agent, data in sorted(agents.items(), key=lambda x: -x[1]["total_tokens"]):
            bar = "█" * min(int(data["total_tokens"] / max(totals["total_tokens"], 1) * 20), 20)
            print(f"    {agent:<20} {data['total_tokens']:>7,} tok  ${data['cost_usd']:.4f}  {bar}")

        print()
        print("  By model:")
        for model, data in sorted(models.items(), key=lambda x: -x[1]["total_tokens"]):
            print(f"    {model:<30} {data['total_tokens']:>7,} tok  ${data['cost_usd']:.4f}")

        if records:
            print()
            print("  Recent calls:")
            for r in records[-5:]:
                ts = r["ts"][:16].replace("T", " ")
                print(f"    {ts}  {r['agent']:<20} "
                      f"in:{r['input_tokens']:>5}  out:{r['output_tokens']:>5}  "
                      f"${r['cost_usd']:.5f}")

        print("═" * 58 + "\n")

    def export_csv(self, path: str = "data/token_usage.csv") -> str:
        """Export all usage records to CSV for spreadsheet analysis."""
        import csv
        records = self._load_all()
        if not records:
            print("[TokenTracker] No records to export.")
            return path
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        print(f"[TokenTracker] Exported {len(records)} records to {path}")
        return path

    # ── Budget alert ───────────────────────────────────────────────────────

    def check_budget(self, daily_limit_usd: float = 5.0) -> bool:
        """
        Check if today's spending exceeds a daily budget.
        Returns True if within budget, False if over.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        today_records = [
            r for r in self._load_all()
            if r["ts"][:10] == today
        ]
        today_cost = sum(r["cost_usd"] for r in today_records)
        if today_cost > daily_limit_usd:
            print(f"\n  [TokenTracker] ⚠ Daily budget exceeded: "
                  f"${today_cost:.4f} / ${daily_limit_usd:.2f}")
            return False
        remaining = daily_limit_usd - today_cost
        print(f"  [TokenTracker] Budget: ${today_cost:.4f} spent today, "
              f"${remaining:.4f} remaining (limit ${daily_limit_usd:.2f})")
        return True

    # ── Internals ──────────────────────────────────────────────────────────

    def _aggregate(self, records: list[dict]) -> dict:
        if not records:
            return {
                "calls": 0, "input_tokens": 0,
                "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0,
            }
        return {
            "calls":         len(records),
            "input_tokens":  sum(r["input_tokens"]  for r in records),
            "output_tokens": sum(r["output_tokens"] for r in records),
            "total_tokens":  sum(r["total_tokens"]  for r in records),
            "cost_usd":      round(sum(r["cost_usd"] for r in records), 6),
        }

    def _load_all(self) -> list[dict]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _append_to_file(self, record: dict) -> None:
        records = self._load_all()
        records.append(record)
        with open(self._file, "w") as f:
            json.dump(records, f, indent=2)
