"""
ToolRegistry
────────────
Wraps all external integrations. Each method tries the real API first;
if credentials are absent or the call fails it falls back to demo data.

Integrations:
  • Jira   — fetch tickets, create/update tickets
  • GitHub — fetch PR diffs
  • Slack  — post messages, post rich blocks, read channel history,
             upload files, list channels, resolve user names
"""

from __future__ import annotations

import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
import os
from typing import Any

from copilot.config import Config
from copilot.guardrails import hitl_gate, AuditLogger


class ToolRegistry:
    def __init__(self, config: Config):
        self.config = config
        self.audit = AuditLogger()

    # ── Jira ──────────────────────────────────────────────────────────────

    def fetch_jira_tickets(self, jql: str = "project = CURRENT AND sprint in openSprints()") -> list[dict]:
        """Fetch open sprint tickets from Jira."""
        try:
            import requests
            from requests.auth import HTTPBasicAuth

            url = f"{self.config.jira_url}/rest/api/3/search"
            auth = HTTPBasicAuth(self.config.jira_user, self.config.jira_token)
            params = {"jql": jql, "maxResults": 50,
                      "fields": "summary,status,assignee,priority,story_points"}
            resp = requests.get(url, params=params, auth=auth, timeout=10)
            resp.raise_for_status()
            issues = resp.json().get("issues", [])
            self.audit.log_tool_call("fetch_jira_tickets", success=True)
            return [
                {
                    "id": i["key"],
                    "summary": i["fields"]["summary"],
                    "status": i["fields"]["status"]["name"],
                    "assignee": (i["fields"].get("assignee") or {}).get("displayName", "Unassigned"),
                    "priority": i["fields"]["priority"]["name"],
                }
                for i in issues
            ]
        except Exception as exc:
            self.audit.log_tool_call("fetch_jira_tickets", success=False, error=str(exc))
            print(f"[Tools] Jira unavailable ({exc}), using demo data.")
            return self.demo_tickets()

    def demo_tickets(self) -> list[dict]:
        return [
            {"id": "PROJ-101", "summary": "User authentication via OAuth2",        "status": "In Progress", "assignee": "Alice",     "priority": "High",   "points": 5},
            {"id": "PROJ-102", "summary": "Dashboard widget for sprint velocity",   "status": "To Do",       "assignee": "Bob",       "priority": "Medium", "points": 3},
            {"id": "PROJ-103", "summary": "Fix pagination bug in ticket list",      "status": "In Progress", "assignee": "Alice",     "priority": "High",   "points": 2},
            {"id": "PROJ-104", "summary": "Write unit tests for risk analyser",     "status": "To Do",       "assignee": "Charlie",   "priority": "Medium", "points": 3},
            {"id": "PROJ-105", "summary": "Integrate Slack notifications",          "status": "To Do",       "assignee": "Unassigned","priority": "Low",    "points": 4},
            {"id": "PROJ-106", "summary": "Set up CI/CD pipeline for staging",      "status": "Blocked",     "assignee": "Bob",       "priority": "High",   "points": 5},
            {"id": "PROJ-107", "summary": "Performance optimisation vector search", "status": "To Do",       "assignee": "Charlie",   "priority": "Medium", "points": 4},
        ]

    # ── GitHub ────────────────────────────────────────────────────────────

    def fetch_pr_diff(self, pr_number: int | str) -> str:
        """Fetch a PR diff from GitHub."""
        try:
            import requests

            url = f"https://api.github.com/repos/{self.config.github_repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"Bearer {self.config.github_token}",
                "Accept": "application/vnd.github.diff",
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            self.audit.log_tool_call("fetch_pr_diff", success=True)
            return resp.text[:4000]
        except Exception as exc:
            self.audit.log_tool_call("fetch_pr_diff", success=False, error=str(exc))
            print(f"[Tools] GitHub unavailable ({exc}), using demo diff.")
            return self.demo_pr_diff()

    def demo_pr_diff(self) -> str:
        return """\
diff --git a/copilot/memory.py b/copilot/memory.py
--- a/copilot/memory.py
+++ b/copilot/memory.py
@@ -45,6 +45,8 @@ class MemoryManager:
     def store_memory(self, category, content, source=""):
+        if not content.strip():
+            return
         entry = Memory(category=category, content=content, source=source)
-        self._ltm[category].append({"content": content})
+        record = {
+            "category": entry.category,
+            "content": entry.content,
+            "source": entry.source,
+            "timestamp": entry.timestamp,
+        }
+        self._ltm[category].append(record)
         self._vector_store.add(content, record)
         self._save_ltm()
"""

    # ── Slack — core helper ───────────────────────────────────────────────

    def _slack_is_configured(self) -> bool:
        return bool(self.config.slack_token and
                    self.config.slack_token.startswith("xoxb-"))

    def _slack_post(self, payload: dict) -> dict:
        """
        Low-level POST to Slack API. Returns the parsed JSON response.
        Raises RuntimeError if Slack returns ok=false.
        """
        import requests
        headers = {
            "Authorization": f"Bearer {self.config.slack_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack error: {data.get('error', 'unknown')}")
        return data

    # ── Slack — post plain text ───────────────────────────────────────────

    @hitl_gate("post_slack_message")
    def post_slack_message(self, text: str, channel: str | None = None) -> bool:
        """
        Post a plain-text message to Slack.
        Requires human approval (HITL gate) before sending.

        Usage:
            tools.post_slack_message("Sprint planning at 10 AM tomorrow.")
            tools.post_slack_message("Blocker on PROJ-106", channel="#blockers")
        """
        if not self._slack_is_configured():
            print(f"[Slack] No token configured. Message: {text[:80]}")
            self.audit.log_tool_call("post_slack_message", success=False,
                                     error="no token")
            return False
        try:
            target = channel or self.config.slack_channel
            self._slack_post({"channel": target, "text": text})
            self.audit.log_tool_call("post_slack_message", success=True)
            print(f"[Slack] ✓ Posted to {target}")
            return True
        except Exception as exc:
            self.audit.log_tool_call("post_slack_message", success=False,
                                     error=str(exc))
            print(f"[Slack] ✗ Failed: {exc}")
            return False

    # ── Slack — post rich Block Kit message ───────────────────────────────

    @hitl_gate("post_slack_message")
    def post_slack_blocks(self, blocks: list[dict],
                          text: str = "",
                          channel: str | None = None) -> bool:
        """
        Post a rich Block Kit message to Slack.
        Requires human approval (HITL gate) before sending.

        Usage:
            tools.post_slack_blocks(
                text="Standup digest",
                blocks=[
                    {"type": "header", "text": {"type": "plain_text", "text": "Daily Standup"}},
                    {"type": "section", "text": {"type": "mrkdwn",
                     "text": "*Completed:* PROJ-103 fix merged"}},
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn",
                     "text": ":warning: *Blocker:* PROJ-106 CI/CD blocked"}},
                ]
            )
        """
        if not self._slack_is_configured():
            print("[Slack] No token configured — skipping block post.")
            return False
        try:
            target = channel or self.config.slack_channel
            self._slack_post({
                "channel": target,
                "text": text,          # fallback for notifications
                "blocks": blocks,
            })
            self.audit.log_tool_call("post_slack_blocks", success=True)
            print(f"[Slack] ✓ Rich message posted to {target}")
            return True
        except Exception as exc:
            self.audit.log_tool_call("post_slack_blocks", success=False,
                                     error=str(exc))
            print(f"[Slack] ✗ Failed: {exc}")
            return False

    # ── Slack — post standup digest (pre-formatted) ───────────────────────

    def post_standup_digest(self, digest: str,
                            channel: str | None = None) -> bool:
        """
        Format and post a standup digest as a rich Slack message.
        Parses sections (Completed / In Progress / Blockers / Upcoming)
        and uses Block Kit for visual formatting.

        Usage:
            tools.post_standup_digest(standup_agent_output)
        """
        blocks = self._format_digest_blocks(digest)
        return self.post_slack_blocks(
            blocks=blocks,
            text="Daily Standup Digest",
            channel=channel,
        )

    def _format_digest_blocks(self, digest: str) -> list[dict]:
        """Convert plain-text digest into Slack Block Kit blocks."""
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📋 Daily Standup Digest"},
            },
            {"type": "divider"},
        ]
        section_icons = {
            "completed":   "✅",
            "in progress": "🔄",
            "blocker":     "🚨",
            "risk":        "⚠️",
            "upcoming":    "📅",
            "nudge":       "👋",
        }
        for line in digest.split("\n"):
            line = line.strip()
            if not line:
                continue
            icon = ""
            for keyword, emoji in section_icons.items():
                if keyword in line.lower():
                    icon = emoji + "  "
                    break
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": icon + line},
            })
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn",
                          "text": "_Generated by AI PM Copilot_"}],
        })
        return blocks

    # ── Slack — read channel history ──────────────────────────────────────

    def fetch_slack_messages(self, channel: str | None = None,
                             limit: int = 20) -> list[dict]:
        """
        Fetch recent messages from a Slack channel.
        Used by the standup agent to summarise recent activity.

        Usage:
            messages = tools.fetch_slack_messages(limit=10)
        """
        if not self._slack_is_configured():
            return self._demo_slack_messages()
        try:
            import requests
            target = channel or self.config.slack_channel
            headers = {"Authorization": f"Bearer {self.config.slack_token}"}
            resp = requests.get(
                "https://slack.com/api/conversations.history",
                headers=headers,
                params={"channel": target, "limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "unknown"))
            self.audit.log_tool_call("fetch_slack_messages", success=True)
            return [
                {"user": m.get("user", "unknown"),
                 "text": m.get("text", ""),
                 "ts":   m.get("ts", "")}
                for m in data.get("messages", [])
            ]
        except Exception as exc:
            self.audit.log_tool_call("fetch_slack_messages", success=False,
                                     error=str(exc))
            print(f"[Slack] fetch_slack_messages failed ({exc}), using demo.")
            return self._demo_slack_messages()

    def _demo_slack_messages(self) -> list[dict]:
        return [
            {"user": "alice", "text": "PROJ-103 pagination fix merged ✓", "ts": "1720000000"},
            {"user": "bob",   "text": "PROJ-106 still waiting on DevOps access", "ts": "1720001000"},
            {"user": "charlie", "text": "Started unit tests for risk analyser", "ts": "1720002000"},
        ]

    # ── Slack — list channels ─────────────────────────────────────────────

    def list_slack_channels(self) -> list[dict]:
        """
        List all public Slack channels the bot has access to.

        Usage:
            channels = tools.list_slack_channels()
            print([c['name'] for c in channels])
        """
        if not self._slack_is_configured():
            return [{"id": "C001", "name": "dev-updates"},
                    {"id": "C002", "name": "dev-standup"}]
        try:
            import requests
            headers = {"Authorization": f"Bearer {self.config.slack_token}"}
            resp = requests.get(
                "https://slack.com/api/conversations.list",
                headers=headers,
                params={"types": "public_channel", "limit": 100},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("error"))
            return [{"id": c["id"], "name": c["name"]}
                    for c in data.get("channels", [])]
        except Exception as exc:
            print(f"[Slack] list_channels failed: {exc}")
            return []

    # ── Slack — resolve user name ─────────────────────────────────────────

    def get_slack_user_name(self, user_id: str) -> str:
        """
        Resolve a Slack user ID to a display name.

        Usage:
            name = tools.get_slack_user_name("U012AB3CD")
        """
        if not self._slack_is_configured():
            return user_id
        try:
            import requests
            headers = {"Authorization": f"Bearer {self.config.slack_token}"}
            resp = requests.get(
                "https://slack.com/api/users.info",
                headers=headers,
                params={"user": user_id},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return (data["user"].get("real_name")
                        or data["user"].get("name", user_id))
        except Exception:
            pass
        return user_id
