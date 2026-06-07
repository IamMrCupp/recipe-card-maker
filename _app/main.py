"""FastAPI application entry point for the recipe app backend.

Phase 3 §3.A.1 (skeleton) + §3.B.1 (read API). Exposes:
  GET /health                         liveness probe
  GET /recipes?category=&tag=         list (summaries), optional filters
  GET /search?q=                      free-text search (summaries)
  GET /recipes/{id}                   one recipe (detail: markdown + structure)

The backend reuses the build tooling in ``_tools/`` (parser, PDF builders) as
library code; importing the ``_app`` package puts ``_tools/`` on sys.path
(see __init__). The store lives on ``app.state`` — injected for tests, otherwise
created lazily — so importing this module / hitting ``/health`` never touches a
real DB file.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from _app.schemas import RecipeDetail, RecipeSummary
from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import RecipeStore


def get_store(request: Request) -> RecipeStore:
    """Dependency: the app's RecipeStore, created lazily on first use if unset."""
    store = request.app.state.store
    if store is None:
        store = SQLiteRecipeStore()
        request.app.state.store = store
    return store


StoreDep = Annotated[RecipeStore, Depends(get_store)]


def create_app(store: RecipeStore | None = None) -> FastAPI:
    """Build the FastAPI app. Pass a `store` in tests; otherwise one is created lazily."""
    app = FastAPI(title="recipe-card-maker", version="0.1.0")
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe — confirms the backend is up."""
        return {"status": "ok"}

    @app.get("/recipes", response_model=list[RecipeSummary])
    def list_recipes(store: StoreDep, category: str | None = None, tag: str | None = None):
        return [RecipeSummary.from_stored(s) for s in store.list(category=category, tag=tag)]

    @app.get("/search", response_model=list[RecipeSummary])
    def search_recipes(store: StoreDep, q: str):
        return [RecipeSummary.from_stored(s) for s in store.search(q)]

    @app.get("/recipes/{recipe_id}", response_model=RecipeDetail)
    def get_recipe(store: StoreDep, recipe_id: str):
        stored = store.get(recipe_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="recipe not found")
        return RecipeDetail.from_stored(stored)

    return app


app = create_app()
