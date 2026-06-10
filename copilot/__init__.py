"""
copilot package

Puts the project root on sys.path so sub-module imports always resolve.
Import classes directly from their modules, e.g.:

    from copilot.config import Config
    from copilot.memory import MemoryManager
    from copilot.orchestrator import Orchestrator
"""

import os
import sys

_PACKAGE_DIR  = os.path.dirname(os.path.abspath(__file__))  # .../copilot/
_PROJECT_ROOT = os.path.dirname(_PACKAGE_DIR)               # .../ai_pm_copilot/

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
