"""
conftest.py — automatically picked up by pytest.
Inserts the project root into sys.path so `import copilot.*` works
no matter which directory pytest is invoked from.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
