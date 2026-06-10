"""
Tests for AI PM Copilot
Run: python -m pytest tests/ -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure the project root is on sys.path regardless of where pytest is invoked from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from copilot.config import Config
from copilot.memory import MemoryManager, VectorStore
from copilot.tools import ToolRegistry


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    def test_missing_api_key(self):
        cfg = Config()
        cfg.anthropic_api_key = ""
        self.assertIn("ANTHROPIC_API_KEY", cfg.validate())

    def test_valid_config(self):
        cfg = Config()
        cfg.anthropic_api_key = "sk-test"
        self.assertEqual(cfg.validate(), [])


# ── VectorStore ───────────────────────────────────────────────────────────────

class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.vs = VectorStore()

    def test_empty_search(self):
        results = self.vs.search("anything")
        self.assertEqual(results, [])

    def test_add_and_search(self):
        self.vs.add("sprint planning velocity backlog", {"category": "signals", "content": "sprint planning velocity backlog"})
        self.vs.add("oauth authentication login user", {"category": "project", "content": "oauth authentication login user"})
        results = self.vs.search("sprint velocity", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("sprint", results[0]["content"])

    def test_top_k_respected(self):
        for i in range(10):
            self.vs.add(f"document number {i} about projects", {"category": "project", "content": f"doc {i}"})
        results = self.vs.search("document project", top_k=3)
        self.assertLessEqual(len(results), 3)

    def test_score_present(self):
        self.vs.add("risk blocker deadline", {"category": "signals", "content": "risk blocker deadline"})
        results = self.vs.search("risk blocker")
        if results:
            self.assertIn("score", results[0])

    def test_size(self):
        self.assertEqual(self.vs.size(), 0)
        self.vs.add("test", {"content": "test"})
        self.assertEqual(self.vs.size(), 1)


# ── MemoryManager ─────────────────────────────────────────────────────────────

class TestMemoryManager(unittest.TestCase):
    def _make_manager(self):
        cfg = Config()
        cfg.anthropic_api_key = "sk-test"
        cfg.stm_max_turns = 6
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg.ltm_path = os.path.join(tmpdir, "ltm.json")
            cfg.vector_store_path = os.path.join(tmpdir, "vectors.json")
            mgr = MemoryManager(cfg)
            mgr._tmpdir = tmpdir        # keep reference alive
        return mgr

    def setUp(self):
        cfg = Config()
        cfg.anthropic_api_key = "sk-test"
        cfg.stm_max_turns = 6
        self._tmpdir = tempfile.TemporaryDirectory()
        cfg.ltm_path = os.path.join(self._tmpdir.name, "ltm.json")
        cfg.vector_store_path = os.path.join(self._tmpdir.name, "vectors.json")
        self.mgr = MemoryManager(cfg)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_add_and_get_turns(self):
        self.mgr.add_turn("user", "hello")
        self.mgr.add_turn("assistant", "hi there")
        turns = self.mgr.get_turns()
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[1]["content"], "hi there")

    def test_store_and_retrieve_memory(self):
        self.mgr.store_memory("project", "We are building an auth module using OAuth2.", source="test")
        results = self.mgr.retrieve("OAuth2 authentication")
        self.assertGreater(len(results), 0)
        self.assertIn("OAuth2", results[0]["content"])

    def test_invalid_category_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.store_memory("invalid_cat", "some content")

    def test_stm_compression_triggers(self):
        for i in range(7):          # exceeds stm_max_turns=6
            self.mgr.add_turn("user", f"message {i}")
            self.mgr.add_turn("assistant", f"reply {i}")
        # After compression, STM should be smaller than the raw total
        self.assertLess(len(self.mgr.get_turns()), 14)
        # And compressed category should have an entry
        compressed = self.mgr.retrieve_category("compressed")
        self.assertGreater(len(compressed), 0)

    def test_ltm_persistence(self):
        self.mgr.store_memory("decisions", "Use PostgreSQL over MongoDB for structured queries.")
        # Re-load from disk
        from copilot.config import Config as Cfg
        cfg2 = Cfg()
        cfg2.anthropic_api_key = "sk-test"
        cfg2.ltm_path = self.mgr.config.ltm_path
        cfg2.vector_store_path = self.mgr.config.vector_store_path
        mgr2 = MemoryManager(cfg2)
        decisions = mgr2.retrieve_category("decisions")
        self.assertTrue(any("PostgreSQL" in e["content"] for e in decisions))

    def test_retrieve_returns_all_categories(self):
        self.mgr.store_memory("project", "Sprint goal: ship auth feature")
        self.mgr.store_memory("team", "Alice is on leave next week")
        self.mgr.store_memory("signals", "High risk: CI pipeline failing intermittently")
        results = self.mgr.retrieve("sprint risk team")
        self.assertGreater(len(results), 0)


# ── ToolRegistry (demo mode) ──────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        cfg = Config()
        cfg.anthropic_api_key = "sk-test"
        cfg.jira_url = ""
        cfg.github_token = ""
        cfg.slack_token = ""
        self.tools = ToolRegistry(cfg)

    def test_demo_tickets_structure(self):
        tickets = self.tools.demo_tickets()
        self.assertIsInstance(tickets, list)
        self.assertGreater(len(tickets), 0)
        required_keys = {"id", "summary", "status", "assignee", "priority"}
        for ticket in tickets:
            self.assertTrue(required_keys.issubset(ticket.keys()))

    def test_demo_pr_diff_nonempty(self):
        diff = self.tools.demo_pr_diff()
        self.assertIn("diff", diff)
        self.assertIn("memory.py", diff)

    def test_fetch_jira_falls_back_to_demo(self):
        """With no Jira credentials, should return demo data without raising."""
        tickets = self.tools.fetch_jira_tickets()
        self.assertIsInstance(tickets, list)
        self.assertGreater(len(tickets), 0)

    def test_post_slack_without_token(self):
        """Without a token, post_slack_message should return False gracefully."""
        result = self.tools.post_slack_message("test message")
        self.assertFalse(result)


# ── Orchestrator (mocked LLM) ─────────────────────────────────────────────────

class TestOrchestratorRouting(unittest.TestCase):
    def setUp(self):
        cfg = Config()
        cfg.anthropic_api_key = "sk-test"
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg.ltm_path = os.path.join(tmpdir, "ltm.json")
            cfg.vector_store_path = os.path.join(tmpdir, "vectors.json")
            self._tmpdir = tempfile.TemporaryDirectory()
            cfg.ltm_path = os.path.join(self._tmpdir.name, "ltm.json")
            cfg.vector_store_path = os.path.join(self._tmpdir.name, "vectors.json")
        self.cfg = cfg

    def tearDown(self):
        self._tmpdir.cleanup()

    @patch("anthropic.Anthropic")
    def test_general_chat_routing(self, mock_anthropic_cls):
        """Orchestrator should call direct_reply when no agents are selected."""
        from copilot.orchestrator import Orchestrator


        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # Route response: no agents
        route_resp = MagicMock()
        route_resp.content = [MagicMock(text='{"intent": "general_chat", "agents": [], "context_needed": []}')]
        # Direct reply response
        direct_resp = MagicMock()
        direct_resp.content = [MagicMock(text="Hello! How can I help?")]

        mock_client.messages.create.side_effect = [route_resp, direct_resp]

        memory = MemoryManager(self.cfg)
        orch = Orchestrator(self.cfg, memory)

        import asyncio
        result = asyncio.run(orch.run("Hello!"))
        self.assertEqual(result, "Hello! How can I help?")

    @patch("anthropic.Anthropic")
    def test_agent_routing_sprint(self, mock_anthropic_cls):
        """Orchestrator should invoke sprint_planner for sprint requests."""
        from copilot.orchestrator import Orchestrator


        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        route_resp = MagicMock()
        route_resp.content = [MagicMock(text='{"intent": "plan sprint", "agents": ["sprint_planner"], "context_needed": ["tickets"]}')]

        agent_resp = MagicMock()
        agent_resp.content = [MagicMock(text="Sprint plan: PROJ-101 (5pts), PROJ-103 (2pts)...")]

        gate_resp = MagicMock()
        gate_resp.content = [MagicMock(text='{"status": "approved"}')]

        mock_client.messages.create.side_effect = [route_resp, agent_resp, gate_resp]

        memory = MemoryManager(self.cfg)
        orch = Orchestrator(self.cfg, memory)

        import asyncio
        result = asyncio.run(orch.run("Plan the next sprint"))
        self.assertIn("Sprint plan", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
