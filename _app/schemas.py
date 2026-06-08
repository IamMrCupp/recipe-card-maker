"""API response models (Pydantic) for the recipe backend.

These shape what the PWA reads. `RecipeSummary` is the list/search row;
`RecipeDetail` adds the canonical markdown plus the parsed structure (intro +
sections) for rendering. Both are built from a `StoredRecipe` via `from_stored`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from _app.storage import Provenance, StoredRecipe


class RecipeCreate(BaseModel):
    """Request body for creating a recipe. Content is canonical markdown."""

    markdown: str
    source: Provenance = Provenance.HAND
    # Optional corpus category (folder). If omitted, falls back to the frontmatter
    # `category`; if neither is present the recipe lives in the DB without a file
    # location until one is assigned.
    category: str | None = None


class RecipeUpdate(BaseModel):
    """Request body for updating a recipe's content."""

    markdown: str


class WebsiteImportRequest(BaseModel):
    """Request body for importing a recipe from a URL (§3.D.2)."""

    url: str


class SocialImportRequest(BaseModel):
    """Request body for importing a recipe from pasted text (§3.D.4)."""

    text: str


class ImportDraft(BaseModel):
    """An unsaved draft returned by an importer — markdown for the §C editor."""

    markdown: str


class ImportCapabilities(BaseModel):
    """What smart import can offer, so the frontend can gate entries (§3.D.3)."""

    llm_extraction: bool


class SectionOut(BaseModel):
    name: str
    intro: str
    blocks: dict[str, list[str]]
    prose: list[str]


class RecipeSummary(BaseModel):
    id: str
    title: str
    category: str | None
    tags: list[str]
    source: str
    source_url: str | None
    rel_path: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredRecipe) -> RecipeSummary:
        return cls(
            id=stored.id,
            title=stored.title,
            category=stored.category,
            tags=stored.tags,
            source=stored.source.value,
            source_url=stored.source_url,
            rel_path=stored.rel_path,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )


class RecipeDetail(RecipeSummary):
    markdown: str
    intro: str
    sections: list[SectionOut]

    @classmethod
    def from_stored(cls, stored: StoredRecipe) -> RecipeDetail:
        recipe = stored.recipe  # parse once
        return cls(
            id=stored.id,
            title=stored.title,
            category=stored.category,
            tags=stored.tags,
            source=stored.source.value,
            source_url=stored.source_url,
            rel_path=stored.rel_path,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            markdown=stored.markdown,
            intro=recipe.intro,
            sections=[
                SectionOut(name=s.name, intro=s.intro, blocks=s.blocks, prose=s.prose)
                for s in recipe.sections
            ],
        )
