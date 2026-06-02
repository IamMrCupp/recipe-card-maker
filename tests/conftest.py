"""Pytest configuration.

Adds the repo's `_tools/` directory to `sys.path` so tests can import the
build helpers (`recipe_parser`, `make_full_pdf`, etc.) directly — the same
pattern the build scripts themselves use.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "_tools"

sys.path.insert(0, str(TOOLS_DIR))
