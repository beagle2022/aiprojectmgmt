"""
ingest.py — Interactive data ingestion tool.

Run anytime to add new data without touching seed.py:

    python ingest.py                    # interactive menu
    python ingest.py --text "..."       # ingest a single fact
    python ingest.py --notes notes.txt  # ingest a meeting notes file
    python ingest.py --csv tickets.csv  # ingest a Jira CSV export
    python ingest.py --show             # print all stored memories
    python ingest.py --reset            # wipe LTM and start fresh
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from copilot.config import Config
from copilot.memory import MemoryManager

CATEGORIES = ["project", "team", "decisions", "signals", "compressed"]

CATEGORY_HINTS = {
    "project":   "Sprint dates, goals, meetings, roadmap, velocity",
    "team":      "Team members, roles, capacity, leave, preferences",
    "decisions": "Architecture choices, approvals, rejected alternatives",
    "signals":   "Tickets, risks, CI status, PR metrics, blockers",
    "compressed":"Meeting notes, session summaries, resolved items",
}


def pick_category() -> str:
    print("\n  Categories:")
    for i, cat in enumerate(CATEGORIES, 1):
        print(f"    {i}. {cat:12s} — {CATEGORY_HINTS[cat]}")
    while True:
        choice = input("\n  Pick category [1-5] › ").strip()
        if choice.isdigit() and 1 <= int(choice) <= 5:
            return CATEGORIES[int(choice) - 1]
        print("  Please enter a number between 1 and 5.")


def ingest_text(memory: MemoryManager, text: str, category: str = None) -> None:
    if not category:
        category = pick_category()
    memory.store_memory(category, text.strip(), source="ingest.py")
    print(f"\n  ✓ Stored in [{category}]: {text[:80]}\n")


def ingest_notes_file(memory: MemoryManager, path: str) -> None:
    with open(path) as f:
        notes = f.read()
    lines = [l.strip() for l in notes.splitlines() if l.strip()]
    title = lines[0] if lines else os.path.basename(path)
    count = 0
    for line in lines[1:]:
        cat = "decisions" if any(
            line.lower().startswith(w)
            for w in ("action", "todo", "decision", "resolved", "agreed")
        ) else "compressed"
        memory.store_memory(cat, f"{title}: {line}", source=path)
        count += 1
    print(f"\n  ✓ Ingested {count} lines from {path}\n")


def ingest_csv_file(memory: MemoryManager, path: str) -> None:
    count = 0
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = "  ·  ".join(f"{k}: {v}" for k, v in row.items() if v.strip())
            memory.store_memory("signals", entry, source=path)
            count += 1
    print(f"\n  ✓ Ingested {count} rows from {path}\n")


def interactive_menu(memory: MemoryManager) -> None:
    print("\n╔══════════════════════════════════════╗")
    print("║   AI PM Copilot — Data Ingestion     ║")
    print("╚══════════════════════════════════════╝")

    while True:
        print("\n  What would you like to do?")
        print("  1. Add a single fact or note")
        print("  2. Paste meeting notes (multi-line)")
        print("  3. Ingest a file (.txt or .csv)")
        print("  4. Show stored memories")
        print("  5. Reset all memory")
        print("  6. Exit")

        choice = input("\n  Choice [1-6] › ").strip()

        if choice == "1":
            text = input("\n  Enter fact › ").strip()
            if text:
                ingest_text(memory, text)

        elif choice == "2":
            print("\n  Paste meeting notes. Type END on a new line when done:")
            lines = []
            while True:
                line = input()
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            notes = "\n".join(lines)
            if notes.strip():
                parsed = [l.strip() for l in notes.splitlines() if l.strip()]
                title = parsed[0] if parsed else "Meeting notes"
                cat = pick_category()
                for line in parsed:
                    memory.store_memory(cat, f"{title}: {line}", source="paste")
                print(f"\n  ✓ Stored {len(parsed)} lines.\n")

        elif choice == "3":
            path = input("\n  File path › ").strip().strip('"')
            if not os.path.exists(path):
                print(f"  File not found: {path}")
                continue
            if path.endswith(".csv"):
                ingest_csv_file(memory, path)
            else:
                ingest_notes_file(memory, path)

        elif choice == "4":
            memory.dump()

        elif choice == "5":
            confirm = input("\n  This will delete all stored memories. Type YES to confirm › ")
            if confirm.strip().upper() == "YES":
                ltm_path = memory.config.ltm_path
                if os.path.exists(ltm_path):
                    os.remove(ltm_path)
                    print("\n  ✓ Memory reset. Restart the copilot.\n")
                else:
                    print("\n  Nothing to reset.\n")

        elif choice == "6":
            print("\n  Goodbye.\n")
            break
        else:
            print("  Please enter a number between 1 and 6.")


def main():
    parser = argparse.ArgumentParser(description="AI PM Copilot data ingestion")
    parser.add_argument("--text",  help="Ingest a single text fact")
    parser.add_argument("--cat",   help="Category for --text (project/team/decisions/signals/compressed)")
    parser.add_argument("--notes", help="Path to a .txt meeting notes file")
    parser.add_argument("--csv",   help="Path to a .csv ticket export")
    parser.add_argument("--show",  action="store_true", help="Show all stored memories")
    parser.add_argument("--reset", action="store_true", help="Wipe all long-term memory")
    args = parser.parse_args()

    config = Config()
    memory = MemoryManager(config)

    if args.show:
        memory.dump()
    elif args.reset:
        if os.path.exists(config.ltm_path):
            os.remove(config.ltm_path)
            print("Memory reset.")
    elif args.text:
        ingest_text(memory, args.text, args.cat)
    elif args.notes:
        ingest_notes_file(memory, args.notes)
    elif args.csv:
        ingest_csv_file(memory, args.csv)
    else:
        interactive_menu(memory)


if __name__ == "__main__":
    main()
