"""
seed.py — Pre-load real project data into long-term memory.

Edit the DATA dict below with your actual project information,
then run ONCE before starting the copilot:

    cd D:\AI-CapstoneProjects
    python data\seed.py

After running, start the copilot normally:
    python main.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.config import Config
from copilot.memory import MemoryManager

# ── Edit everything below with your real data ─────────────────────────────────

DATA = {

    "project": [
        "Project name: AI PM Copilot. Goal: ship agentic project management tool by Q3 2026.",
        "Sprint 12 runs from July 7 to July 18 2026. Sprint goal: complete OAuth2 authentication module.",
        "Next sprint planning meeting: Monday July 7 2026 at 10:00 AM IST. Google Meet: meet.google.com/abc-xyz",
        "Next sprint review: Friday July 18 2026 at 4:00 PM IST.",
        "Next sprint retrospective: Friday July 18 2026 at 5:00 PM IST.",
        "Daily standup: every weekday at 9:30 AM IST on Slack huddle #dev-standup.",
        "Definition of done: code reviewed, tests written, deployed to staging, PM sign-off.",
        "Sprint 11 velocity: 34 story points. Sprint 10 velocity: 28 story points.",
        "Current sprint capacity: 36 story points (Alice 12pts, Bob 10pts, Charlie 8pts, Diana 6pts).",
    ],

    "team": [
        "Alice Chen — Backend Engineer. Owns: auth module, API layer. Timezone: IST.",
        "Bob Kumar — Frontend Engineer. Owns: dashboard, UI components. Timezone: IST.",
        "Charlie Singh — QA Engineer. Owns: test coverage, regression suite. Timezone: IST.",
        "Diana Patel — Product Manager. Owns: backlog, stakeholder comms. Timezone: IST.",
        "Alice is on leave July 14-15. Reduces sprint capacity by 4 story points.",
        "Bob prefers async code reviews — allow 24hrs before expecting feedback.",
        "Charlie flags: test environment is flaky on Windows, use Docker for reliable runs.",
    ],

    "decisions": [
        "Decision: Use PostgreSQL over MongoDB. Rationale: structured queries for sprint metrics. Date: June 2026.",
        "Decision: OAuth2 with Google provider over custom auth. Rationale: faster delivery, better security. Date: June 2026.",
        "Decision: TF-IDF vector store over Pinecone. Rationale: no external dependency, sufficient for MVP. Date: June 2026.",
        "Decision: Anthropic Claude Sonnet as reasoning model. Rationale: best cost/quality ratio. Date: June 2026.",
        "Rejected: LangChain — too heavy, adds unnecessary abstractions for this use case.",
    ],

    "signals": [
        "PROJ-101 OAuth2 login — 5pts — Alice — High — In Progress.",
        "PROJ-102 Dashboard velocity widget — 3pts — Bob — Medium — To Do.",
        "PROJ-103 Fix pagination bug — 2pts — Alice — High — In Progress.",
        "PROJ-104 Unit tests for risk analyser — 3pts — Charlie — Medium — To Do.",
        "PROJ-105 Integrate Slack notifications — 4pts — Unassigned — Low — To Do.",
        "PROJ-106 CI/CD pipeline for staging — 5pts — Bob — High — Blocked: waiting on DevOps access.",
        "PROJ-107 Vector search optimisation — 4pts — Charlie — Medium — To Do.",
        "Risk: PROJ-106 blocked on DevOps staging access. ETA unknown. Impact: HIGH.",
        "Risk: Alice leave July 14-15 reduces sprint capacity by 4pts. Affects PROJ-101 timeline.",
        "CI pipeline: GitHub Actions passing on main. Flaky integration test failure rate: 8%.",
        "PR cycle time average last sprint: 18 hours. Target: under 12 hours.",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────


def main():
    config = Config()
    missing = config.validate()
    if missing:
        print(f"[Error] Missing: {', '.join(missing)}. Add ANTHROPIC_API_KEY to .env first.")
        sys.exit(1)

    memory = MemoryManager(config)
    total = 0

    print("\nSeeding long-term memory...\n")
    for category, entries in DATA.items():
        for entry in entries:
            memory.store_memory(category, entry, source="seed.py")
            print(f"  [{category}] {entry[:72]}{'...' if len(entry) > 72 else ''}")
            total += 1

    print(f"\n✓ Stored {total} entries across {len(DATA)} categories.")
    print("  Run  python main.py  to start the copilot with this data loaded.\n")
    memory.dump()


if __name__ == "__main__":
    main()
