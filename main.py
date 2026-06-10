"""
AI PM Copilot — Main entry point

Usage:
    python main.py          # from inside ai_pm_copilot/
    python -m copilot       # from project root
    pm-copilot              # after: pip install -e .
"""

import asyncio
import os
import sys

# ── Guarantee the project root is on sys.path ─────────────────────────────────
# _HERE  = .../ai_pm_copilot          (the folder containing main.py)
# Python needs _HERE on sys.path so that `import copilot.xxx` resolves to
# .../ai_pm_copilot/copilot/xxx.py
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# ─────────────────────────────────────────────────────────────────────────────

# Import each class directly from its own module file — never rely on __init__
# re-exports, which can silently fail if a stale package is cached elsewhere.
from copilot.config import Config               # noqa: E402
from copilot.memory import MemoryManager        # noqa: E402
from copilot.orchestrator import Orchestrator   # noqa: E402


async def main() -> None:
    config = Config()
    missing = config.validate()
    if missing:
        print(f"[Error] Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env, add your ANTHROPIC_API_KEY, then retry.")
        sys.exit(1)

    memory = MemoryManager(config)
    orchestrator = Orchestrator(config, memory)

    print("\n╔══════════════════════════════════════╗")
    print("║      AI Project Management Copilot   ║")
    print("╚══════════════════════════════════════╝")
    print("Commands: 'memory' — inspect LTM | 'exit' — quit\n")

    while True:
        try:
            user_input = input("You › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("Goodbye.")
            break
        if user_input.lower() == "memory":
            memory.dump()
            continue

        response = await orchestrator.run(user_input)
        print(f"\nCopilot › {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
