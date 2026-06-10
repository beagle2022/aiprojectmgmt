"""
Allows running the copilot as a module:  python -m copilot
Also used by the pm-copilot console script installed via pyproject.toml.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.orchestrator import Orchestrator
from copilot.memory import MemoryManager
from copilot.config import Config


async def _main():
    config = Config()
    missing = config.validate()
    if missing:
        print(f"[Error] Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the values, then retry.")
        sys.exit(1)

    memory = MemoryManager(config)
    orchestrator = Orchestrator(config, memory)

    print("\n╔══════════════════════════════════════╗")
    print("║      AI Project Management Copilot   ║")
    print("╚══════════════════════════════════════╝")
    print("Type 'exit' to quit, 'memory' to inspect LTM.\n")

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


def run():
    asyncio.run(_main())


if __name__ == "__main__":
    run()
