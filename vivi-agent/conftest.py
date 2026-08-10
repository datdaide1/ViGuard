"""Repo-wide pytest bootstrap: put `src/` and the repo root on sys.path.

Centralizing this here (pytest auto-loads conftest.py before collecting any
test) means individual test modules can `import vivi_agent....` or
`import src.vivi_agent....` without each one manipulating `sys.path` itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_PATH = str(Path(__file__).resolve().parent)
SRC_PATH = str(Path(__file__).resolve().parent / "src")

for path in (SRC_PATH, ROOT_PATH):
    if path not in sys.path:
        sys.path.insert(0, path)
