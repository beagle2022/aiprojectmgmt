"""
seed.py — Bulk-load real project data into long-term memory.

HOW TO USE:
  1. Edit the DATA sections below with your real project info
  2. Run once:  python data/seed.py
  3. Start app: python main.py

To reset and re-seed:
  del data\ltm.json        (Windows)
  rm data/ltm.json         (Mac/Linux)
  python data/seed.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.config import Config
from copilot.memory import MemoryManager


# ════════════════════════════════════════════════════════════════
# EDIT EVERYTHING BELOW WITH YOUR REAL PROJECT DATA
# ════════════════════════════════════════════════════════════════

DATA = {

    # ── Project facts ─────────────────────────────────────────
    # Sprint dates, goals, meetings, velocity, definition of done
    "project": [
        "Project name: AI PM Copilot. Goal: ship agentic project management tool by Q3 2026.",
        "Sprint 13 runs from July 21 to August 1 2026. Sprint goal: ship vector search optimisation and Slack integration.",
        "Sprint planning meeting: Monday July 21 2026 at 10:00 AM IST. Google Meet: meet.google.com/abc-xyz",
        "Sprint review: Friday August 1 2026 at 4:00 PM IST.",
        "Sprint retrospective: Friday August 1 2026 at 5:00 PM IST.",
        "Daily standup: every weekday at 9:30 AM IST on Slack #dev-standup.",
        "Sprint duration: 2 weeks (10 working days).",
        "Definition of done: code reviewed, unit tests written, deployed to staging, PM sign-off.",
        "Sprint 12 velocity: 26 story points delivered. Sprint 11 velocity: 34 story points.",
        "Team capacity per sprint: 36 story points (Alice 12, Bob 10, Charlie 8, Diana 6).",
        "Roadmap: Q3 milestone is complete authentication + CI/CD pipeline + Slack integration.",
        "Tech stack: Python 3.12, Anthropic Claude API, FastAPI (planned), PostgreSQL (planned).",
    ],

    # ── Team knowledge ────────────────────────────────────────
    # Names, roles, skills, availability, preferences
    "team": [
        "Alice Chen — Backend Engineer. Owns: auth module, orchestrator, API layer. 12 pts capacity. Timezone: IST.",
        "Bob Kumar — Frontend Engineer. Owns: dashboard, UI components, CI/CD. 10 pts capacity. Timezone: IST.",
        "Charlie Singh — QA Engineer. Owns: test coverage, regression suite, vector search. 8 pts capacity. Timezone: IST.",
        "Diana Patel — Product Manager. Owns: backlog, stakeholder comms, sprint ceremonies. 6 pts capacity. Timezone: IST.",
        "Alice is on leave July 14-15 2026. Effective sprint 12 capacity reduced by 4 pts.",
        "Bob needs DevOps team approval before PROJ-106 CI/CD can proceed.",
        "Charlie uses Docker for test runs — Windows environment is flaky.",
        "Diana runs all sprint ceremonies. Prefers async updates via Slack.",
        "Team uses IST timezone. Core hours: 10am–6pm IST Monday to Friday.",
        "Code review SLA: 24 hours. PRs idle >24hrs get a nudge from the standup agent.",
    ],

    # ── Decisions and architecture ────────────────────────────
    # Technical decisions, rejected alternatives, approvals
    "decisions": [
        "Decision: Use PostgreSQL over MongoDB. Rationale: structured queries for sprint metrics. Date: June 2026. Approved by: Diana.",
        "Decision: OAuth2 with Google provider. Rationale: faster delivery, better security than custom auth. Date: June 2026.",
        "Decision: TF-IDF vector store for MVP. Rationale: no external dependency. Upgrade to neural embeddings post-MVP. Date: June 2026.",
        "Decision: Anthropic Claude Sonnet as reasoning model. Rationale: best cost-quality ratio. Date: June 2026.",
        "Decision: 2-week sprint cadence. Rationale: balances delivery frequency with planning overhead. Date: May 2026.",
        "Rejected: LangChain — too heavy, adds unnecessary abstractions. Decision: use Anthropic SDK directly.",
        "Rejected: Pinecone vector DB — adds external dependency. Revisit after MVP.",
        "Rejected: 3-week sprints — team prefers tighter feedback loops.",
        "Architecture: 5-layer system — UI, Orchestrator, Agents, Tools, Memory. See HLD document.",
        "Security: all API keys in .env, never in code. OAuth2 for all integrations. HITL gate on write actions.",
    ],

    # ── Code and quality signals ──────────────────────────────
    # Current tickets, CI status, risks, PR metrics
    "signals": [
        "PROJ-101 OAuth2 login — 5 pts — Alice — High — Carry-over from Sprint 12 — In Progress.",
        "PROJ-102 Dashboard velocity widget — 3 pts — Bob — Medium — Carry-over from Sprint 12 — To Do.",
        "PROJ-103 Fix pagination bug — 2 pts — Alice — High — Done in Sprint 12.",
        "PROJ-104 Unit tests for risk analyser — 3 pts — Charlie — Medium — To Do.",
        "PROJ-105 Integrate Slack notifications — 4 pts — Unassigned — Low — To Do.",
        "PROJ-106 CI/CD pipeline for staging — 5 pts — Bob — High — Blocked: waiting on DevOps access.",
        "PROJ-107 Vector search performance optimisation — 4 pts — Charlie — Medium — To Do.",
        "Risk: PROJ-106 blocked on external DevOps team. ETA unknown. Impact: HIGH. Mitigation: escalate to Diana.",
        "Risk: Alice leave July 14-15 reduces sprint 12 capacity by 4 pts. Affects PROJ-101 delivery timeline.",
        "CI pipeline: GitHub Actions on main branch. Flaky integration test failure rate: 8% last week.",
        "PR cycle time: 18 hours average last sprint. Target is under 12 hours.",
        "Test coverage: 74% overall. Risk analyser module has lowest coverage at 41%.",
        "Tech debt: memory.py TF-IDF implementation should be replaced with sentence-transformers post-MVP.",
    ],

}

# ════════════════════════════════════════════════════════════════
# ADDITIONAL INGEST METHODS — paste meeting notes or CSV below
# ════════════════════════════════════════════════════════════════

MEETING_NOTES = """
Sprint 12 retrospective — July 18 2026

What went well:
  PROJ-103 pagination bug fixed ahead of schedule.
  Team communication via Slack was effective.

What needs improvement:
  PROJ-106 has been blocked for 2 weeks — needs escalation process.
  PR review times too slow — averaging 18hrs, target is 12hrs.

Action items:
  Bob to follow up with DevOps by July 22.
  Team agrees to add PR review to daily standup agenda.
  Charlie to improve test coverage on risk analyser to 70% by Sprint 13.
"""

JIRA_CSV = """
id,summary,status,assignee,priority,points
PROJ-101,OAuth2 login,In Progress,Alice,High,5
PROJ-102,Dashboard velocity widget,To Do,Bob,Medium,3
PROJ-104,Unit tests risk analyser,To Do,Charlie,Medium,3
PROJ-107,Vector search optimisation,To Do,Charlie,Medium,4
"""


# ════════════════════════════════════════════════════════════════
# ENGINE — do not edit below this line
# ════════════════════════════════════════════════════════════════

def ingest_dict(memory: MemoryManager, data: dict) -> int:
    """Ingest a {category: [entries]} dict into LTM."""
    total = 0
    for category, entries in data.items():
        for entry in entries:
            memory.store_memory(category, entry.strip(), source="seed.py")
            print(f"  [{category:12s}] {entry[:70]}{'...' if len(entry)>70 else ''}")
            total += 1
    return total


def ingest_meeting_notes(memory: MemoryManager, notes: str) -> int:
    """
    Parse free-form meeting notes into LTM.
    Each non-empty line becomes a 'compressed' memory entry.
    Action items go into 'decisions'.
    """
    if not notes.strip():
        return 0
    total = 0
    lines = [l.strip() for l in notes.strip().splitlines() if l.strip()]
    title = lines[0] if lines else "Meeting notes"
    for line in lines[1:]:
        if line.lower().startswith(("action", "todo", "follow")):
            cat = "decisions"
        else:
            cat = "compressed"
        entry = f"{title}: {line}"
        memory.store_memory(cat, entry, source="meeting_notes")
        print(f"  [{'decisions' if cat=='decisions' else 'compressed':12s}] {entry[:70]}...")
        total += 1
    return total


def ingest_csv(memory: MemoryManager, csv_text: str) -> int:
    """
    Parse a simple CSV of tickets into LTM signals.
    Expected columns: id, summary, status, assignee, priority, points
    """
    if not csv_text.strip():
        return 0
    import csv, io
    total = 0
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    for row in reader:
        entry = (
            f"{row.get('id','?')} {row.get('summary','?')} — "
            f"{row.get('points','?')} pts — {row.get('assignee','?')} — "
            f"{row.get('priority','?')} — {row.get('status','?')}."
        )
        memory.store_memory("signals", entry, source="jira_csv")
        print(f"  [signals     ] {entry[:70]}")
        total += 1
    return total


def main():
    config = Config()
    missing = config.validate()
    if missing:
        print(f"\n[Error] Missing: {', '.join(missing)}")
        print("Add ANTHROPIC_API_KEY to .env and retry.\n")
        sys.exit(1)

    memory = MemoryManager(config)
    total = 0

    print("\n" + "═"*60)
    print("  AI PM Copilot — Data Ingestion")
    print("═"*60)

    print("\n[1/3] Ingesting structured project data...")
    total += ingest_dict(memory, DATA)

    print("\n[2/3] Ingesting meeting notes...")
    total += ingest_meeting_notes(memory, MEETING_NOTES)

    print("\n[3/3] Ingesting Jira CSV export...")
    total += ingest_csv(memory, JIRA_CSV)

    print("\n" + "═"*60)
    print(f"  Done. {total} entries stored across all LTM categories.")
    print("═"*60)
    print("\nMemory summary:")
    memory.dump()
    print("\nRun  python main.py  to start the copilot with this data.\n")


if __name__ == "__main__":
    main()
