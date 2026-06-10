"""
ToolRegistry
────────────
Wraps all external integrations. Each method tries the real API first;
if credentials are absent or the call fails it falls back to demo data
so the copilot can be explored without any third-party accounts.

Real integrations:
  • Jira (fetch_jira_tickets)
  • GitHub (fetch_pr_diff)
  • Slack  (post_slack_message)

Demo stubs:
  • demo_tickets()
  • demo_pr_diff()
"""

from __future__ import annotations


import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
from typing import Any

from copilot.config import Config
from copilot.guardrails import hitl_gate, AuditLogger
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
            params = {"jql": jql, "maxResults": 50, "fields": "summary,status,assignee,priority,story_points"}
            resp = requests.get(url, params=params, auth=auth, timeout=10)
            resp.raise_for_status()
            issues = resp.json().get("issues", [])
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
            print(f"[Tools] Jira unavailable ({exc}), using demo data.")
            return self.demo_tickets()

    def demo_tickets(self) -> list[dict]:
        return [
            {"id": "PROJ-101", "summary": "User authentication via OAuth2", "status": "In Progress", "assignee": "Alice", "priority": "High", "points": 5},
            {"id": "PROJ-102", "summary": "Dashboard widget for sprint velocity", "status": "To Do", "assignee": "Bob", "priority": "Medium", "points": 3},
            {"id": "PROJ-103", "summary": "Fix pagination bug in ticket list", "status": "In Progress", "assignee": "Alice", "priority": "High", "points": 2},
            {"id": "PROJ-104", "summary": "Write unit tests for risk analyser", "status": "To Do", "assignee": "Charlie", "priority": "Medium", "points": 3},
            {"id": "PROJ-105", "summary": "Integrate Slack notifications", "status": "To Do", "assignee": "Unassigned", "priority": "Low", "points": 4},
            {"id": "PROJ-106", "summary": "Set up CI/CD pipeline for staging", "status": "Blocked", "assignee": "Bob", "priority": "High", "points": 5},
            {"id": "PROJ-107", "summary": "Performance optimisation for vector search", "status": "To Do", "assignee": "Charlie", "priority": "Medium", "points": 4},
        ]

    # ── GitHub ────────────────────────────────────────────────────────────

    def fetch_pr_diff(self, pr_number: int | str) -> str:
        """Fetch a PR diff from GitHub."""
        try:
            import requests

            repo = self.config.github_repo
            token = self.config.github_token
            url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.diff",
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.text[:4000]          # truncate for context budget
        except Exception as exc:
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

    # ── Slack ─────────────────────────────────────────────────────────────

    @hitl_gate("post_slack_message")
    def post_slack_message(self, text: str, channel: str | None = None) -> bool:
        """Post a message to Slack. Requires human approval before sending."""
        target = channel or self.config.slack_channel
        try:
            import requests

            url = "https://slack.com/api/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.config.slack_token}"}
            payload = {"channel": target, "text": text}
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("error", "unknown"))
            print(f"[Tools] Posted to Slack {target}.")
            return True
        except Exception as exc:
            print(f"[Tools] Slack unavailable ({exc}). Message would have been:\n  {text[:80]}")
            return False
