"""Tests for the recipe storage layer (_app/sqlite_store.py).

Phase 3 §3.A.2 — round-trips a recipe through the store (create → get →
list/search → update → delete) and confirms the queryable columns are
denormalized from the markdown content.
"""

from __future__ import annotations

import pytest

from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import Provenance

CAKE_MD = """---
title: Erdbeertorte
category: cakes
tags: [strawberry, summer]
---
# Erdbeertorte

A strawberry cake.

## Yield and timing
- 8 servings
"""

COOKIE_MD = """---
title: Sun and Moon Cookies
category: cookies
tags: [marzipan]
---
# Sun and Moon Cookies

## Yield and timing
- 24 cookies
"""


@pytest.fixture
def store(tmp_path):
    return SQLiteRecipeStore(db_path=tmp_path / "test.db")


def test_create_and_get_round_trip(store):
    created = store.create(CAKE_MD, source=Provenance.HAND)
    assert created.id
    assert created.created_at == created.updated_at
    assert created.source is Provenance.HAND

    fetched = store.get(created.id)
    assert fetched is not None
    assert fetched.markdown == CAKE_MD
    # the envelope exposes the parsed view
    assert fetched.title == "Erdbeertorte"
    assert fetched.category == "cakes"
    assert fetched.tags == ["strawberry", "summer"]
    assert fetched.recipe.section("Yield and timing") is not None


def test_get_missing_returns_none(store):
    assert store.get("does-not-exist") is None


def test_list_orders_by_title_and_filters(store):
    store.create(COOKIE_MD, source=Provenance.HAND)
    store.create(CAKE_MD, source=Provenance.IMPORT)

    all_recipes = store.list()
    assert [r.title for r in all_recipes] == ["Erdbeertorte", "Sun and Moon Cookies"]

    assert [r.title for r in store.list(category="cakes")] == ["Erdbeertorte"]
    assert [r.title for r in store.list(tag="marzipan")] == ["Sun and Moon Cookies"]
    assert store.list(category="nope") == []


def test_search_matches_title_and_body(store):
    store.create(CAKE_MD, source=Provenance.HAND)
    store.create(COOKIE_MD, source=Provenance.HAND)

    assert [r.title for r in store.search("strawberry")] == ["Erdbeertorte"]  # body match
    assert [r.title for r in store.search("cookies")] == ["Sun and Moon Cookies"]  # title match
    assert store.search("zzz") == []


def test_update_refreshes_content_and_columns(store):
    created = store.create(CAKE_MD, source=Provenance.HAND)
    updated = store.update(created.id, markdown=COOKIE_MD)
    assert updated is not None
    assert updated.title == "Sun and Moon Cookies"
    assert updated.category == "cookies"
    assert updated.updated_at >= created.updated_at
    # search now finds it under the new content, not the old
    assert [r.title for r in store.search("marzipan")] == ["Sun and Moon Cookies"]


def test_update_images_and_source_url(store):
    created = store.create(CAKE_MD, source=Provenance.WEBSITE)
    updated = store.update(
        created.id, source_url="https://example.com/torte", images=["a.jpg", "b.jpg"]
    )
    assert updated is not None
    assert updated.source_url == "https://example.com/torte"
    assert updated.images == ["a.jpg", "b.jpg"]
    assert updated.markdown == CAKE_MD  # unchanged when not provided


def test_update_missing_returns_none(store):
    assert store.update("does-not-exist", markdown=CAKE_MD) is None


def test_delete(store):
    created = store.create(CAKE_MD, source=Provenance.HAND)
    assert store.delete(created.id) is True
    assert store.get(created.id) is None
    assert store.delete(created.id) is False


def test_persists_across_store_instances(tmp_path):
    db = tmp_path / "persist.db"
    rid = SQLiteRecipeStore(db_path=db).create(CAKE_MD, source=Provenance.HAND).id
    # a fresh store object on the same file sees the data
    assert SQLiteRecipeStore(db_path=db).get(rid) is not None


def test_nfs_pragmas_applied_when_env_set(tmp_path, monkeypatch):
    """RCM_SQLITE_NFS=1 (the hosted 4α deploy) forces NFS-safe journal settings."""
    from sqlalchemy import text

    monkeypatch.setenv("RCM_SQLITE_NFS", "1")
    store = SQLiteRecipeStore(db_path=tmp_path / "nfs.db")
    with store.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "truncate"
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 2  # FULL


def test_default_journal_mode_unchanged_without_env(tmp_path):
    from sqlalchemy import text

    store = SQLiteRecipeStore(db_path=tmp_path / "plain.db")
    with store.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "delete"
