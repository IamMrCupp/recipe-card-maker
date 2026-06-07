"""API response models (Pydantic) for the recipe backend.

These shape what the PWA reads. `RecipeSummary` is the list/search row;
`RecipeDetail` adds the canonical markdown plus the parsed structure (intro +
sections) for rendering. Both are built from a `StoredRecipe` via `from_stored`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from _app.storage import StoredRecipe


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
