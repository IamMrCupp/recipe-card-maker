"""Storage layer: the recipe domain envelope + the store interface.

Phase 3 invariants this file encodes:
  1. The database is the source of truth; markdown + PDF are exports. A recipe's
     canonical content is stored as **markdown text** and parsed back to a
     `Recipe` on read (recipe_parser stays the single structural authority).
  2. Storage sits behind the `RecipeStore` interface, so swapping SQLite for
     Postgres (or anything else) later is an adapter, not a migration.

`StoredRecipe` is a *thin extension* of the parser's `Recipe`, not a fork: it
wraps the markdown content with the fields the app needs but the frontmatter
doesn't carry — a stable id, timestamps, provenance, and image references. The
parsed `Recipe` is available via the `.recipe` property.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from recipe_parser import Recipe, parse_recipe_text


class Provenance(str, Enum):
    """How a recipe entered the collection."""

    HAND = "hand"
    WEBSITE = "website"
    PHOTO = "photo"
    SOCIAL = "social"
    IMPORT = "import"  # bulk-imported from the existing markdown corpus (§3.A.3)


@dataclass
class StoredRecipe:
    """A recipe as the store sees it: canonical markdown + storage envelope."""

    id: str
    markdown: str
    source: Provenance
    created_at: datetime
    updated_at: datetime
    source_url: str | None = None
    images: list[str] = field(default_factory=list)  # image refs; populated in §3.E
    rel_path: str | None = None  # corpus-relative path, e.g. "cakes/erdbeertorte.md" (§3.A.3)

    @property
    def recipe(self) -> Recipe:
        """Parse the canonical markdown into the structured domain model."""
        return parse_recipe_text(self.markdown)

    @property
    def title(self) -> str:
        return self.recipe.title

    @property
    def category(self) -> str | None:
        cat = self.recipe.meta.get("category")
        return cat if isinstance(cat, str) else None

    @property
    def tags(self) -> list[str]:
        return normalize_tags(self.recipe.meta.get("tags"))


def normalize_tags(raw: object) -> list[str]:
    """Coerce a frontmatter `tags` value (list / scalar / None) into list[str]."""
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


class RecipeStore(ABC):
    """Persistence interface. Implementations: SQLiteRecipeStore (others later)."""

    @abstractmethod
    def create(
        self,
        markdown: str,
        *,
        source: Provenance,
        source_url: str | None = None,
        images: list[str] | None = None,
        rel_path: str | None = None,
    ) -> StoredRecipe:
        """Persist a new recipe and return it with its assigned id + timestamps."""

    @abstractmethod
    def get(self, recipe_id: str) -> StoredRecipe | None:
        """Fetch one recipe by id, or None if it doesn't exist."""

    @abstractmethod
    def list(self, *, category: str | None = None, tag: str | None = None) -> list[StoredRecipe]:
        """List recipes, optionally filtered by category and/or tag. Ordered by title."""

    @abstractmethod
    def search(self, query: str) -> list[StoredRecipe]:
        """Free-text search over title + content. Ordered by title."""

    @abstractmethod
    def update(
        self,
        recipe_id: str,
        *,
        markdown: str | None = None,
        source_url: str | None = None,
        images: list[str] | None = None,
        rel_path: str | None = None,
    ) -> StoredRecipe | None:
        """Update only the provided fields. Returns the updated recipe, or None if absent."""

    @abstractmethod
    def delete(self, recipe_id: str) -> bool:
        """Delete a recipe. Returns True if a row was removed."""
