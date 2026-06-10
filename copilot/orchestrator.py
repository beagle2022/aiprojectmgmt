"""
Orchestrator
────────────
The central reasoning agent. Implements a lightweight ReAct loop:

  1. Retrieve relevant LTM via RAG.
  2. Ask the reasoning LLM to classify the intent and select agent(s).
  3. Dispatch selected agents (sequentially; parallelism is an extension).
  4. Aggregate results.
  5. Evaluate: if complete → return + persist; if incomplete → retry once.
  6. Persist key facts to LTM on session end.

The orchestrator also maintains the conversation history (STM) and injects
retrieved memories into the system prompt for every turn.
"""

from __future__ import annotations


import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
from typing import Any

import anthropic

from copilot.agents import AGENT_REGISTRY, BaseAgent
from copilot.config import Config
from copilot.memory import MemoryManager
from copilot.guardrails import SecurityPipeline

# ── Intent → agent mapping ────────────────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """\
You are the routing layer of an AI Project Management Copilot.
Given a user message and a list of available agents, respond ONLY with a
JSON object in this exact format (no markdown fences, no extra keys):

{
  "intent": "<one-line description of what the user wants>",
  "agents": ["<agent_name>", ...],
  "context_needed": ["<key>", ...]
}

Available agents:
- requirements      Drafts PRDs, user stories, acceptance criteria
- sprint_planner    Plans sprints, ranks backlog, estimates velocity
- risk_analyst      Identifies blockers, dependencies, deadline risk
- code_reviewer     Reviews PRs, flags bugs, applies quality gate
- standup           Generates daily digest, nudges, status summary

If none of the agents are needed (e.g. the user is just chatting), return:
{"intent": "general_chat", "agents": [], "context_needed": []}
"""

class Orchestrator:
    MAX_RETRIES = 1

    def __init__(self, config: Config, memory: MemoryManager):
        self.config = config
        self.memory = memory
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self._agents: dict[str, BaseAgent] = {
            name: cls(config) for name, cls in AGENT_REGISTRY.items()
        }
        self.security = SecurityPipeline()

    # ── Main entry point ──────────────────────────────────────────────────

    async def run(self, user_message: str) -> str:
        # 0. Security pipeline — sanitise, rate-limit, redact PII
        user_message, blocked = self.security.process_input(user_message)
        if blocked:
            return "[Request blocked by security guardrails. Please rephrase and try again.]"

        # 1. Persist the user turn
        self.memory.add_turn("user", user_message)

        # 2. Retrieve relevant LTM
        retrieved = self.memory.retrieve(user_message)
        memory_context = self._format_retrieved(retrieved)

        # 3. Route intent → agents
        routing = self._route(user_message, memory_context)

        if not routing.get("agents"):
            # General conversation — answer directly
            reply = self._direct_reply(user_message, memory_context)
            self.memory.add_turn("assistant", reply)
            return reply

        # 4. Dispatch agents
        agent_results = self._dispatch(routing["agents"], user_message)

        # 5. Aggregate
        aggregated = self._aggregate(user_message, routing["intent"], agent_results)

        # 6. Review gate
        for attempt in range(self.MAX_RETRIES + 1):
            gate = self._review_gate(aggregated)
            if gate["status"] == "approved" or attempt == self.MAX_RETRIES:
                break
            # Retry with refined sub-query
            refined = gate.get("refined_query", user_message)
            extra_results = self._dispatch(routing["agents"], refined)
            agent_results.update(extra_results)
            aggregated = self._aggregate(user_message, routing["intent"], agent_results)

        # 7. Persist outcomes to LTM
        self._persist_to_ltm(routing["intent"], aggregated, agent_results)

        # 8. Persist assistant turn
        aggregated = self.security.process_output(aggregated)
        self.memory.add_turn("assistant", aggregated)
        return aggregated

    # ── Routing ───────────────────────────────────────────────────────────

    def _route(self, message: str, memory_context: str) -> dict:
        messages = [
            {
                "role": "user",
                "content": (
                    f"Memory context:\n{memory_context}\n\n"
                    f"User message: {message}"
                ),
            }
        ]
        resp = self.client.messages.create(
            model=self.config.reasoning_model,
            max_tokens=256,
            system=INTENT_SYSTEM_PROMPT,
            messages=messages,
        )
        raw = resp.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract JSON substring
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
        return {"intent": "general_chat", "agents": [], "context_needed": []}

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _dispatch(self, agent_names: list[str], task: str) -> dict[str, str]:
        results: dict[str, str] = {}
        for name in agent_names:
            agent = self._agents.get(name)
            if not agent:
                results[name] = f"[Agent '{name}' not found]"
                continue
            print(f"  → [{name}] running…")
            context = self._build_agent_context(name)
            try:
                results[name] = agent.run(task, context)
            except Exception as exc:
                results[name] = f"[{name} error: {exc}]"
        return results

    def _build_agent_context(self, agent_name: str) -> dict:
        """Build a context dict tailored to each agent type."""
        context: dict[str, Any] = {
            "project_info": self.memory.retrieve_category("project")[-3:],
            "team_info": self.memory.retrieve_category("team")[-3:],
            "past_decisions": self.memory.retrieve_category("decisions")[-3:],
        }
        if agent_name == "sprint_planner":
            context["signals"] = self.memory.retrieve_category("signals")[-5:]
        elif agent_name == "risk_analyst":
            context["signals"] = self.memory.retrieve_category("signals")[-5:]
            context["compressed"] = self.memory.retrieve_category("compressed")[-3:]
        return context

    # ── Aggregation ───────────────────────────────────────────────────────

    def _aggregate(self, user_message: str, intent: str, agent_results: dict[str, str]) -> str:
        if len(agent_results) == 1:
            return next(iter(agent_results.values()))

        parts = "\n\n".join(
            f"[{name.replace('_', ' ').title()}]\n{result}"
            for name, result in agent_results.items()
        )
        system = (
            "You are the Orchestrator of an AI PM Copilot. "
            "Multiple specialist agents have responded to the user's request. "
            "Merge their outputs into a single coherent, well-formatted reply. "
            "Resolve any conflicts. Remove redundancy. Preserve all important details. "
            "Do not add preamble like 'Here is a combined response'."
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"Original request: {user_message}\n"
                    f"Intent: {intent}\n\n"
                    f"Agent outputs:\n{parts}"
                ),
            }
        ]
        resp = self.client.messages.create(
            model=self.config.reasoning_model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return resp.content[0].text.strip()

    # ── Review gate ───────────────────────────────────────────────────────

    def _review_gate(self, response: str) -> dict:
        """
        Returns {"status": "approved"} or
                {"status": "retry", "refined_query": "..."}
        """
        system = (
            "You are a quality gate for an AI PM Copilot response. "
            "Evaluate whether the response fully and specifically answers the user's request. "
            "Respond ONLY with JSON: "
            '{"status": "approved"} or '
            '{"status": "retry", "refined_query": "<more specific follow-up query>"}'
        )
        resp = self.client.messages.create(
            model=self.config.reasoning_model,
            max_tokens=128,
            system=system,
            messages=[{"role": "user", "content": response}],
        )
        raw = resp.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "approved"}

    # ── Direct reply (general chat) ───────────────────────────────────────

    def _direct_reply(self, message: str, memory_context: str) -> str:
        history = self.memory.get_turns()[-10:]   # last 10 turns
        system = (
            "You are a friendly, concise AI Project Management Copilot. "
            "You help software development teams plan, execute, and ship. "
            f"Relevant memory:\n{memory_context or 'None yet.'}"
        )
        messages = history + [{"role": "user", "content": message}]
        resp = self.client.messages.create(
            model=self.config.reasoning_model,
            max_tokens=512,
            system=system,
            messages=messages,
        )
        return resp.content[0].text.strip()

    # ── LTM persistence ───────────────────────────────────────────────────

    def _persist_to_ltm(self, intent: str, response: str, agent_results: dict) -> None:
        """Write key outcomes to the appropriate LTM categories."""
        # Decisions made by the risk agent
        if "risk_analyst" in agent_results:
            self.memory.store_memory(
                "signals",
                f"Risk analysis ({intent}): {agent_results['risk_analyst'][:300]}",
                source="risk_analyst",
            )
        # Requirements → project knowledge
        if "requirements" in agent_results:
            self.memory.store_memory(
                "project",
                f"Requirements ({intent}): {agent_results['requirements'][:300]}",
                source="requirements_agent",
            )
        # Sprint plan → signals
        if "sprint_planner" in agent_results:
            self.memory.store_memory(
                "signals",
                f"Sprint plan ({intent}): {agent_results['sprint_planner'][:300]}",
                source="sprint_planner",
            )

    # ── Utilities ─────────────────────────────────────────────────────────

    def _format_retrieved(self, retrieved: list[dict]) -> str:
        if not retrieved:
            return ""
        lines = []
        for item in retrieved:
            lines.append(f"[{item.get('category', '?')}] {item.get('content', '')[:120]}")
        return "\n".join(lines)

#################RATE LIMITATION########################
self.security = SecurityPipeline(
    rate_limiter=RateLimiter(
        max_calls=config.rate_limit_max_calls,
        window_seconds=config.rate_limit_window,
    ),
    block_on_injection=config.block_on_injection,
)


