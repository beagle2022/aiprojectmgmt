"""
MemoryManager
─────────────
Manages two memory tiers:

  STM (Short-Term Memory)
    • The in-process list of conversation turns for the current session.
    • Auto-compresses when len(turns) > config.stm_max_turns.

  LTM (Long-Term Memory)
    • A JSON file persisted to disk, keyed by category.
    • Categories: project, team, decisions, compressed, signals.

  VectorStore
    • A lightweight in-process vector store using TF-IDF cosine similarity.
    • Falls back gracefully when scikit-learn is not installed (returns empty).
"""

from __future__ import annotations


import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from copilot.config import Config

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Turn:
    role: str          # "user" | "assistant" | "tool"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class Memory:
    category: str      # project | team | decisions | compressed | signals
    content: str
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    embedding: list[float] = field(default_factory=list)

# ── Tiny TF-IDF vector store ──────────────────────────────────────────────────

class VectorStore:
    """
    A minimal TF-IDF + cosine similarity vector store.
    No external dependencies beyond the standard library.
    """

    def __init__(self):
        self._docs: list[str] = []
        self._meta: list[dict] = []

    # ── public API ────────────────────────────────────────────────────────

    def add(self, text: str, meta: dict) -> None:
        self._docs.append(text)
        self._meta.append(meta)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._docs:
            return []
        scores = self._cosine_scores(query)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score >= 0:   # include zero-score when only one doc exists
                results.append({**self._meta[idx], "score": round(score, 4)})
        return results

    def size(self) -> int:
        return len(self._docs)

    # ── internals ─────────────────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def _tf(self, tokens: list[str]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        for t in tokens:
            counts[t] += 1
        n = len(tokens) or 1
        return {t: c / n for t, c in counts.items()}

    def _idf(self, term: str) -> float:
        df = sum(1 for doc in self._docs if term in doc.lower())
        if df == 0:
            return 0.0
        # When only one doc exists, standard IDF collapses to 0; use a floor of 1.0
        return max(1.0, math.log((len(self._docs) + 1) / (df + 1)) + 1)

    def _tfidf_vec(self, text: str) -> dict[str, float]:
        tokens = self._tokenize(text)
        tf = self._tf(tokens)
        return {t: v * self._idf(t) for t, v in tf.items()}

    def _cosine(self, a: dict[str, float], b: dict[str, float]) -> float:
        dot = sum(a.get(k, 0) * v for k, v in b.items())
        mag_a = math.sqrt(sum(v ** 2 for v in a.values())) or 1
        mag_b = math.sqrt(sum(v ** 2 for v in b.values())) or 1
        return dot / (mag_a * mag_b)

    def _cosine_scores(self, query: str) -> list[float]:
        q_vec = self._tfidf_vec(query)
        scores = []
        for doc in self._docs:
            d_vec = self._tfidf_vec(doc)
            scores.append(self._cosine(q_vec, d_vec))
        return scores

# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    CATEGORIES = ("project", "team", "decisions", "compressed", "signals")

    def __init__(self, config: Config):
        self.config = config
        self._stm: list[Turn] = []
        self._ltm: dict[str, list[dict]] = {c: [] for c in self.CATEGORIES}
        self._vector_store = VectorStore()
        self._load_ltm()

    # ── STM ───────────────────────────────────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        self._stm.append(Turn(role=role, content=content))
        if len(self._stm) > self.config.stm_max_turns:
            self._compress_stm()

    def get_turns(self) -> list[dict]:
        return [{"role": t.role, "content": t.content} for t in self._stm]

    def _compress_stm(self) -> None:
        """Summarise oldest half of turns and evict them into LTM."""
        half = len(self._stm) // 2
        old_turns = self._stm[:half]
        self._stm = self._stm[half:]

        summary_lines = []
        for t in old_turns:
            prefix = "User" if t.role == "user" else "Copilot"
            summary_lines.append(f"{prefix}: {t.content[:120]}")
        summary = "Session summary (compressed): " + " | ".join(summary_lines)

        self.store_memory("compressed", summary, source="stm_compression")
        print(f"[Memory] Compressed {half} turns → LTM.")

    # ── LTM ───────────────────────────────────────────────────────────────

    def store_memory(self, category: str, content: str, source: str = "") -> None:
        if category not in self.CATEGORIES:
            raise ValueError(f"Unknown memory category: {category}")
        entry = Memory(category=category, content=content, source=source)
        record = {
            "category": entry.category,
            "content": entry.content,
            "source": entry.source,
            "timestamp": entry.timestamp,
        }
        self._ltm[category].append(record)
        self._vector_store.add(content, record)
        self._save_ltm()

    def retrieve(self, query: str) -> list[dict]:
        """Return top-k semantically relevant LTM entries."""
        return self._vector_store.search(query, top_k=self.config.top_k)

    def retrieve_category(self, category: str) -> list[dict]:
        return self._ltm.get(category, [])

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_ltm(self) -> None:
        path = self.config.ltm_path
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data: dict[str, list] = json.load(f)
            for cat, entries in data.items():
                if cat in self.CATEGORIES:
                    self._ltm[cat] = entries
                    for entry in entries:
                        self._vector_store.add(entry["content"], entry)
        except (json.JSONDecodeError, KeyError):
            print("[Memory] Warning: could not load LTM from disk — starting fresh.")

    def _save_ltm(self) -> None:
        path = self.config.ltm_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._ltm, f, indent=2)

    # ── Introspection ─────────────────────────────────────────────────────

    def dump(self) -> None:
        print("\n── Long-term memory ──────────────────────────────────")
        for cat, entries in self._ltm.items():
            if entries:
                print(f"  [{cat}] {len(entries)} entries")
                for e in entries[-3:]:
                    print(f"    • {e['content'][:90]}")
        print(f"  Vector store size: {self._vector_store.size()} items")
        print(f"  STM turns: {len(self._stm)}")
        print("──────────────────────────────────────────────────────\n")

    def session_summary(self) -> str:
        counts = {c: len(v) for c, v in self._ltm.items()}
        return (
            f"LTM — project:{counts['project']} team:{counts['team']} "
            f"decisions:{counts['decisions']} compressed:{counts['compressed']} "
            f"signals:{counts['signals']} | STM turns:{len(self._stm)}"
        )
