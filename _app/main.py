"""FastAPI application entry point for the recipe app backend.

Phase 3 §3.A.1 (skeleton) + §3.B.1 (read API) + §3.B.2 (serves the PWA).

  GET /health                         liveness probe
  GET /api/recipes?category=&tag=     list (summaries), optional filters
  GET /api/search?q=                  free-text search (summaries)
  GET /api/recipes/{id}               one recipe (detail: markdown + structure)
  GET /<anything else>                the SvelteKit SPA (served from _web/build)

The JSON API lives under ``/api`` so it can't collide with the SPA's own
client-side routes (e.g. the browser path ``/recipes/{id}`` is a page, while
``/api/recipes/{id}`` is its data). Everything not under ``/api`` (or ``/health``
/ ``/docs``) falls through to the SPA, with a fallback to ``index.html`` for
deep links. If the frontend hasn't been built, the API still works.

The backend reuses the build tooling in ``_tools/`` as library code (importing
the ``_app`` package puts ``_tools/`` on sys.path — see __init__). The store
lives on ``app.state`` — injected for tests, otherwise created lazily.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from _app.schemas import RecipeDetail, RecipeSummary
from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import RecipeStore

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_BUILD_DIR = (REPO_ROOT / "_web" / "build").resolve()

# Some platforms don't know .webmanifest; make sure it's served with a sane type.
mimetypes.add_type("application/manifest+json", ".webmanifest")


def get_store(request: Request) -> RecipeStore:
    """Dependency: the app's RecipeStore, created lazily on first use if unset."""
    store = request.app.state.store
    if store is None:
        store = SQLiteRecipeStore()
        request.app.state.store = store
    return store


StoreDep = Annotated[RecipeStore, Depends(get_store)]


def create_app(store: RecipeStore | None = None, web_build_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app. Pass `store` / `web_build_dir` in tests; otherwise defaults apply."""
    app = FastAPI(title="recipe-card-maker", version="0.1.0")
    app.state.store = store
    build_dir = (web_build_dir or WEB_BUILD_DIR).resolve()

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe — confirms the backend is up."""
        return {"status": "ok"}

    api = APIRouter(prefix="/api")

    @api.get("/recipes", response_model=list[RecipeSummary])
    def list_recipes(store: StoreDep, category: str | None = None, tag: str | None = None):
        return [RecipeSummary.from_stored(s) for s in store.list(category=category, tag=tag)]

    @api.get("/search", response_model=list[RecipeSummary])
    def search_recipes(store: StoreDep, q: str):
        return [RecipeSummary.from_stored(s) for s in store.search(q)]

    @api.get("/recipes/{recipe_id}", response_model=RecipeDetail)
    def get_recipe(store: StoreDep, recipe_id: str):
        stored = store.get(recipe_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="recipe not found")
        return RecipeDetail.from_stored(stored)

    app.include_router(api)
    _mount_spa(app, build_dir)
    return app


def _mount_spa(app: FastAPI, build_dir: Path) -> None:
    """Serve the built SvelteKit SPA, falling back to index.html for client routes."""
    if not build_dir.is_dir():
        return  # frontend not built — API-only mode

    index = build_dir / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Unknown /api paths are a 404, not the SPA shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (build_dir / full_path).resolve()
        if full_path and candidate.is_file() and build_dir in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
