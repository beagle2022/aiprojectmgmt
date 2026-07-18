"""
Agents
──────
Base class + five specialist agents:
  RequirementsAgent   — PRDs, user stories, acceptance criteria
  SprintPlannerAgent  — backlog ranking, velocity, sprint plan
  RiskAnalystAgent    — blockers, dependencies, deadline risk
  CodeReviewerAgent   — PR summarisation, quality gate, bug flags
  StandupAgent        — daily digest, nudges, status summary

Each agent receives a task string + context dict and returns a plain-text result.
Tool calls are simulated when real credentials are absent (demo mode).
"""

from __future__ import annotations


import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from copilot.config import Config
from copilot.tools import ToolRegistry

class BaseAgent(ABC):
    """All specialist agents inherit from this."""

    name: str = "base"
    description: str = ""

    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.tools = ToolRegistry(config)   # shared tool registry

    # ── Public ────────────────────────────────────────────────────────────

    def run(self, task: str, context: dict[str, Any]) -> str:
        """Execute the agent and return its output as a string."""
        system = self._system_prompt()
        messages = self._build_messages(task, context)
        return self._call_llm(system, messages)

    # ── To implement ──────────────────────────────────────────────────────

    @abstractmethod
    def _system_prompt(self) -> str: ...

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_messages(self, task: str, context: dict) -> list[dict]:
        ctx_str = json.dumps(context, indent=2) if context else "{}"
        return [
            {
                "role": "user",
                "content": (
                    f"Context:\n{ctx_str}\n\n"
                    f"Task:\n{task}"
                ),
            }
        ]

    def _call_llm(self, system: str, messages: list[dict]) -> str:
        model = (
            self.config.code_model
            if self.name == "code_reviewer"
            else self.config.reasoning_model
        )
        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return response.content[0].text.strip()

# ── Specialist agents ─────────────────────────────────────────────────────────

class RequirementsAgent(BaseAgent):
    name = "requirements"
    description = "Drafts PRDs, user stories, and acceptance criteria."

    def _system_prompt(self) -> str:
        return (
            "You are the Requirements Agent for an AI PM Copilot. "
            "Given a feature request or product goal, produce clear user stories "
            "(As a <role>, I want <goal>, so that <benefit>) with concise acceptance criteria. "
            "If a PRD is needed, structure it with: Overview, Goals, User Stories, "
            "Out of Scope, and Success Metrics. Be specific and measurable. "
            "Respond in plain text or Markdown. Keep it concise."
        )

class SprintPlannerAgent(BaseAgent):
    name = "sprint_planner"
    description = "Plans sprints, ranks the backlog, estimates velocity."

    def _system_prompt(self) -> str:
        return (
            "You are the Sprint Planner Agent for an AI PM Copilot. "
            "Given a list of backlog items, team velocity, and sprint duration, "
            "produce a prioritised sprint plan. "
            "For each ticket include: priority rank, effort estimate (story points), "
            "owner suggestion, and any dependency flags. "
            "Flag if the sprint is over-capacity. "
            "Respond in plain text with a clear table or list."
        )

    def run(self, task: str, context: dict[str, Any]) -> str:
        # Augment context with simulated Jira data if no real integration
        if not context.get("tickets") and self.config.jira_url:
            context["tickets"] = self.tools.fetch_jira_tickets()
        elif not context.get("tickets"):
            context["tickets"] = self.tools.demo_tickets()
        return super().run(task, context)

class RiskAnalystAgent(BaseAgent):
    name = "risk_analyst"
    description = "Identifies blockers, dependencies, and deadline risk."

    def _system_prompt(self) -> str:
        return (
            "You are the Risk Analyst Agent for an AI PM Copilot. "
            "Analyse the provided sprint data, open tickets, CI status, and team context. "
            "Produce a risk register with: Risk ID, Description, Likelihood (H/M/L), "
            "Impact (H/M/L), Risk Score (H×H=Critical, etc.), and Mitigation. "
            "Flag any items that could cause a missed deadline. "
            "Respond concisely in Markdown."
        )

class CodeReviewerAgent(BaseAgent):
    name = "code_reviewer"
    description = "Summarises PRs, flags bug patterns, applies quality gates."

    def _system_prompt(self) -> str:
        return (
            "You are the Code Reviewer Agent for an AI PM Copilot. "
            "Given a PR diff or description, produce: "
            "1) A plain-English summary of what the change does. "
            "2) A list of potential bugs or code smells (with line references if available). "
            "3) A quality gate decision: PASS, PASS WITH COMMENTS, or BLOCK. "
            "4) Up to three actionable review comments. "
            "Be concise, technical, and constructive. "
            "Use Markdown."
        )

    def run(self, task: str, context: dict[str, Any]) -> str:
        if not context.get("pr_diff") and self.config.github_token:
            pr_number = context.get("pr_number")
            if pr_number:
                context["pr_diff"] = self.tools.fetch_pr_diff(pr_number)
        elif not context.get("pr_diff"):
            context["pr_diff"] = self.tools.demo_pr_diff()
        return super().run(task, context)

class StandupAgent(BaseAgent):
    name = "standup"
    description = "Generates daily standup digest, nudges, and status summary."

    def _system_prompt(self) -> str:
        return (
            "You are the Standup Agent for an AI PM Copilot. "
            "Given the team's ticket updates, PR activity, and any blockers, "
            "produce a concise daily standup digest. "
            "Structure: "
            "• Completed yesterday "
            "• In progress today "
            "• Blockers / needs attention "
            "• Nudges (e.g. stale PRs, overdue tickets) "
            "Keep it under 200 words. "
            "Respond in plain text."
        )

    def run(self, task: str, context: dict) -> str:
        # Fetch recent Slack messages to include in context
        if not context.get("slack_messages"):
            context["slack_messages"] = self.tools.fetch_slack_messages(limit=10)
        digest = super().run(task, context)
        # Auto-post digest to Slack after generating it
        self.tools.post_standup_digest(digest)
        return digest

# ── Registry ──────────────────────────────────────────────────────────────────

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "requirements": RequirementsAgent,
    "sprint_planner": SprintPlannerAgent,
    "risk_analyst": RiskAnalystAgent,
    "code_reviewer": CodeReviewerAgent,
    "standup": StandupAgent,
}
