"""
token_report.py — View token usage and cost estimates

USAGE:
    python token_report.py               # full lifetime report
    python token_report.py --session     # current session only
    python token_report.py --today       # today's usage
    python token_report.py --csv         # export to CSV
    python token_report.py --budget 5.0  # check against $5/day budget
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from copilot.token_tracker import TokenTracker


def main():
    parser = argparse.ArgumentParser(description="AI PM Copilot — Token usage report")
    parser.add_argument("--today",  action="store_true", help="Show today's usage only")
    parser.add_argument("--csv",    action="store_true", help="Export all records to CSV")
    parser.add_argument("--budget", type=float, metavar="USD",
                        help="Check daily budget (e.g. --budget 5.0)")
    args = parser.parse_args()

    tracker = TokenTracker()
    all_records = tracker._load_all()

    if not all_records:
        print("\n  No token usage recorded yet.")
        print("  Start the copilot and send a message, then run this report.\n")
        return

    if args.csv:
        tracker.export_csv()
        return

    if args.budget:
        tracker.check_budget(daily_limit_usd=args.budget)

    if args.today:
        today = datetime.now(timezone.utc).date().isoformat()
        records = [r for r in all_records if r["ts"][:10] == today]
        if not records:
            print(f"\n  No usage recorded today ({today}).\n")
            return
        totals = tracker._aggregate(records)
        print(f"\n  Today ({today}): {totals['calls']} calls  "
              f"{totals['total_tokens']:,} tokens  ${totals['cost_usd']:.4f} USD\n")
        tracker.report(scope="all")
    else:
        tracker.report(scope="all")


if __name__ == "__main__":
    main()
