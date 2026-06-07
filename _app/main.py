"""FastAPI application entry point for the recipe app backend.

Phase 3 §3.A.1 — backend skeleton. For now this exposes a single ``/health``
endpoint; read endpoints, the store, and the editor land in later sections.

The backend reuses the existing build tooling in ``_tools/`` (the recipe
parser and the PDF builders) as library code rather than reimplementing it.
``_ensure_tools_on_path()`` mirrors the sys.path shim in tests/conftest.py so
those imports resolve whether the app is launched via ``uvicorn`` or imported
in a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "_tools"


def _ensure_tools_on_path() -> None:
    """Put ``_tools/`` on sys.path so the backend can import the parser + builders."""
    tools = str(TOOLS_DIR)
    if tools not in sys.path:
        sys.path.insert(0, tools)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    _ensure_tools_on_path()
    app = FastAPI(title="recipe-card-maker", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe — confirms the backend is up."""
        return {"status": "ok"}

    return app


app = create_app()
