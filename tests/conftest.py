"""Pytest conftest: add repo root to sys.path so tests can import convert.py."""
import sys
from pathlib import Path

# tests/conftest.py -> repo root is the parent directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
