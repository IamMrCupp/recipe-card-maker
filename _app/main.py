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
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import make_cards_pdf
import make_full_pdf
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from recipe_parser import Recipe, parse_recipe_text

from _app.llm_config import extraction_available
from _app.photo_import import IMAGE_TYPES, MAX_IMAGE_BYTES, import_photo
from _app.schemas import (
    ImportCapabilities,
    ImportDraft,
    RecipeCreate,
    RecipeDetail,
    RecipeSummary,
    RecipeUpdate,
    WebsiteImportRequest,
)
from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import RecipeStore
from _app.web_fetch import FetchError, UnsafeURL
from _app.web_import import ImportUnavailable, import_website

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


def _validated_recipe(markdown: str) -> Recipe:
    """Parse and sanity-check submitted markdown. 422 if it has no usable title."""
    if not markdown.strip():
        raise HTTPException(status_code=422, detail="markdown is empty")
    recipe = parse_recipe_text(markdown)
    has_title = bool(recipe.meta.get("title")) or recipe.title != "untitled"
    if not has_title:
        raise HTTPException(
            status_code=422,
            detail="recipe needs a title (a frontmatter `title:` or an `# H1` heading)",
        )
    return recipe


def _derive_rel_path(recipe: Recipe, category_override: str | None) -> str | None:
    """Corpus location for a new recipe: <category>/<slug>.md, or None if uncategorized."""
    category = category_override
    if not category:
        meta_cat = recipe.meta.get("category")
        category = meta_cat if isinstance(meta_cat, str) and meta_cat else None
    return f"{category}/{recipe.slug}.md" if category else None


def _build_pdf_response(
    store: RecipeStore,
    recipe_id: str,
    build: Callable[[Recipe, Path], None],
    suffix: str,
) -> Response:
    """Render a recipe to PDF via the existing reportlab builder and stream it back."""
    stored = store.get(recipe_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    recipe = stored.recipe
    filename = f"{recipe.slug}{suffix}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / filename
        build(recipe, out)
        data = out.read_bytes()
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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

    @api.post("/recipes", response_model=RecipeDetail, status_code=201)
    def create_recipe(store: StoreDep, body: RecipeCreate):
        recipe = _validated_recipe(body.markdown)
        rel_path = _derive_rel_path(recipe, body.category)
        # Provenance URL is canonical in the markdown frontmatter (importers write
        # it there); surface it onto the queryable DB column at create time.
        source_url = recipe.meta.get("source_url") or None
        stored = store.create(
            body.markdown, source=body.source, rel_path=rel_path, source_url=source_url
        )
        return RecipeDetail.from_stored(stored)

    @api.put("/recipes/{recipe_id}", response_model=RecipeDetail)
    def update_recipe(store: StoreDep, recipe_id: str, body: RecipeUpdate):
        _validated_recipe(body.markdown)
        updated = store.update(recipe_id, markdown=body.markdown)
        if updated is None:
            raise HTTPException(status_code=404, detail="recipe not found")
        return RecipeDetail.from_stored(updated)

    @api.delete("/recipes/{recipe_id}", status_code=204)
    def delete_recipe(store: StoreDep, recipe_id: str):
        if not store.delete(recipe_id):
            raise HTTPException(status_code=404, detail="recipe not found")

    @api.get("/import/capabilities", response_model=ImportCapabilities)
    def import_capabilities():
        """What smart import can offer right now. The frontend gates the photo
        entry on this (photo import is LLM-only — useless without a key)."""
        return ImportCapabilities(llm_extraction=extraction_available())

    @api.post("/import/photo", response_model=ImportDraft)
    async def import_from_photo(file: UploadFile):
        """Turn an uploaded image into an unsaved markdown draft via the §D.1
        vision path. LLM-only — no structural fallback. Image is discarded after."""
        if file.content_type not in IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="unsupported image type")
        data = await file.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="image too large")
        try:
            # Blocking HTTP call to the model — offload off the event loop.
            markdown = await run_in_threadpool(import_photo, data, file.content_type)
            return ImportDraft(markdown=markdown)
        except ImportUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @api.post("/import/website", response_model=ImportDraft)
    def import_from_website(body: WebsiteImportRequest):
        """Turn a URL into an unsaved markdown draft. Structural parse first,
        LLM fallback second — see _app/web_import. Nothing is persisted."""
        if not body.url.strip():
            raise HTTPException(status_code=422, detail="url is empty")
        try:
            return ImportDraft(markdown=import_website(body.url))
        except UnsafeURL as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ImportUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @api.get("/recipes/{recipe_id}/card.pdf")
    def recipe_card_pdf(store: StoreDep, recipe_id: str):
        return _build_pdf_response(store, recipe_id, make_cards_pdf.build_pdf, "_4x6")

    @api.get("/recipes/{recipe_id}/letter.pdf")
    def recipe_letter_pdf(store: StoreDep, recipe_id: str):
        return _build_pdf_response(store, recipe_id, make_full_pdf.build_pdf, "_full")

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
