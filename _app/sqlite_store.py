"""SQLite implementation of RecipeStore (SQLAlchemy 2.0).

The canonical recipe content lives in the ``markdown`` column; ``title``,
``category``, and ``tags`` are denormalized from it on write so list/search/
filter are plain column queries. Parsing on write keeps those columns honest;
the parser stays the single structural authority (see storage.py).

The DB file is a working store, not the source of truth in the portability
sense — it's gitignored, and §3.A.3 exports it back to the markdown corpus.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from recipe_parser import parse_recipe_text
from sqlalchemy import String, Text, create_engine, event, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from _app.storage import Provenance, RecipeStore, StoredRecipe, normalize_tags

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "_app" / "var" / "recipes.db"


class Base(DeclarativeBase):
    pass


class RecipeRow(Base):
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    markdown: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    images: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    rel_path: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # denormalized-from-markdown, for querying:
    title: Mapped[str] = mapped_column(String, default="", index=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; re-attach UTC so callers get aware values."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_stored(row: RecipeRow) -> StoredRecipe:
    return StoredRecipe(
        id=row.id,
        markdown=row.markdown,
        source=Provenance(row.source),
        source_url=row.source_url,
        images=json.loads(row.images),
        rel_path=row.rel_path,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


class SQLiteRecipeStore(RecipeStore):
    """A RecipeStore backed by a SQLite file (or in-memory URL)."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get("RCM_DB_PATH", DEFAULT_DB_PATH)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        if os.environ.get("RCM_SQLITE_NFS"):
            # Hosted deploy (4α): the PVC is NFS-backed. WAL's shm/mmap doesn't
            # behave on NFS, so force the rollback journal + full fsync. Safe with
            # the deployment's single-writer guarantee (1 replica, Recreate).
            @event.listens_for(self.engine, "connect")
            def _nfs_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=TRUNCATE")
                cur.execute("PRAGMA synchronous=FULL")
                cur.close()

        Base.metadata.create_all(self.engine)

    # -- writes ------------------------------------------------------------
    def create(
        self,
        markdown: str,
        *,
        source: Provenance,
        source_url: str | None = None,
        images: list[str] | None = None,
        rel_path: str | None = None,
    ) -> StoredRecipe:
        now = datetime.now(UTC)
        row = RecipeRow(
            id=uuid.uuid4().hex,
            markdown=markdown,
            source=source.value,
            source_url=source_url,
            images=json.dumps(images or []),
            rel_path=rel_path,
            created_at=now,
            updated_at=now,
        )
        _denormalize(row)
        with Session(self.engine) as session:
            session.add(row)
            session.commit()
            return _to_stored(row)

    def update(
        self,
        recipe_id: str,
        *,
        markdown: str | None = None,
        source_url: str | None = None,
        images: list[str] | None = None,
        rel_path: str | None = None,
    ) -> StoredRecipe | None:
        with Session(self.engine) as session:
            row = session.get(RecipeRow, recipe_id)
            if row is None:
                return None
            if markdown is not None:
                row.markdown = markdown
                _denormalize(row)
            if source_url is not None:
                row.source_url = source_url
            if images is not None:
                row.images = json.dumps(images)
            if rel_path is not None:
                row.rel_path = rel_path
            row.updated_at = datetime.now(UTC)
            session.commit()
            return _to_stored(row)

    def delete(self, recipe_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(RecipeRow, recipe_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    # -- reads -------------------------------------------------------------
    def get(self, recipe_id: str) -> StoredRecipe | None:
        with Session(self.engine) as session:
            row = session.get(RecipeRow, recipe_id)
            return _to_stored(row) if row else None

    def list(self, *, category: str | None = None, tag: str | None = None) -> list[StoredRecipe]:
        stmt = select(RecipeRow).order_by(RecipeRow.title)
        if category is not None:
            stmt = stmt.where(RecipeRow.category == category)
        with Session(self.engine) as session:
            rows = session.scalars(stmt).all()
        stored = [_to_stored(r) for r in rows]
        if tag is not None:
            stored = [s for s in stored if tag in s.tags]  # tags is JSON; filter in Python
        return stored

    def search(self, query: str) -> list[StoredRecipe]:
        like = f"%{query}%"
        stmt = (
            select(RecipeRow)
            .where(or_(RecipeRow.title.ilike(like), RecipeRow.markdown.ilike(like)))
            .order_by(RecipeRow.title)
        )
        with Session(self.engine) as session:
            rows = session.scalars(stmt).all()
        return [_to_stored(r) for r in rows]


def _denormalize(row: RecipeRow) -> None:
    """Refresh the queryable columns from the markdown content."""
    recipe = parse_recipe_text(row.markdown)
    cat = recipe.meta.get("category")
    row.title = recipe.title
    row.category = cat if isinstance(cat, str) else None
    row.tags = json.dumps(normalize_tags(recipe.meta.get("tags")))
