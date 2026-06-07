"""FastAPI application entry point for the recipe app backend.

Phase 3 §3.A.1 — backend skeleton. For now this exposes a single ``/health``
endpoint; read endpoints, the store, and the editor land in later sections.

The backend reuses the existing build tooling in ``_tools/`` (the recipe
parser and the PDF builders) as library code rather than reimplementing it;
importing the ``_app`` package puts ``_tools/`` on sys.path (see __init__).
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title="recipe-card-maker", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe — confirms the backend is up."""
        return {"status": "ok"}

    return app


app = create_app()
