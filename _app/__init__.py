"""Recipe app backend (Phase 3).

A FastAPI service that will let recipes be captured (by hand, website, photo,
social), stored, browsed, and printed. See _app/README.md for the layout
rationale and plan.md / phase-3-checklist.md §3 for the roadmap.

The leading underscore is deliberate: it matches the repo's "build-invisible"
convention (_tools/, _templates/) so the recipe scanner in recipe_parser.py
and the Makefile's `find` both skip this directory.

Importing this package puts the repo's ``_tools/`` directory on ``sys.path`` so
backend modules can import the build tooling (recipe_parser, the PDF builders)
as library code — the same shim tests/conftest.py uses. Doing it here, at
package import, means any ``_app`` submodule can rely on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "_tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
