"""
Config — centralised settings loaded from environment variables.
Copy .env.example to .env and fill in your keys before running.
"""


import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # ── Anthropic ──────────────────────────────────────────────────────────
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    reasoning_model: str = field(default_factory=lambda: os.getenv("REASONING_MODEL", "claude-sonnet-4-20250514"))
    code_model: str = field(default_factory=lambda: os.getenv("CODE_MODEL", "claude-sonnet-4-20250514"))

    # ── Memory ─────────────────────────────────────────────────────────────
    ltm_path: str = field(default_factory=lambda: os.getenv("LTM_PATH", "data/ltm.json"))
    vector_store_path: str = field(default_factory=lambda: os.getenv("VECTOR_STORE_PATH", "data/vectors.json"))
    top_k: int = 5                      # RAG retrieval top-k
    stm_max_turns: int = 20             # before compression triggers

    # ── Integrations (optional — omit to run in demo mode) ─────────────────
    jira_url: str = field(default_factory=lambda: os.getenv("JIRA_URL", ""))
    jira_user: str = field(default_factory=lambda: os.getenv("JIRA_USER", ""))
    jira_token: str = field(default_factory=lambda: os.getenv("JIRA_TOKEN", ""))

    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))

    slack_token: str = field(default_factory=lambda: os.getenv("SLACK_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: os.getenv("SLACK_CHANNEL", "#dev-updates"))

    def validate(self) -> list[str]:
        """Return a list of missing required settings."""
        missing = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
