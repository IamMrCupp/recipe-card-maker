"""Tests for the read API (_app/main.py §3.B.1).

Seeds a tmp store, builds the app around it, and exercises list/search/get.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app.main import create_app
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
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    store.create(CAKE_MD, source=Provenance.IMPORT, rel_path="cakes/erdbeertorte.md")
    store.create(COOKIE_MD, source=Provenance.HAND)
    return TestClient(create_app(store))


def test_list_returns_summaries_ordered_by_title(client):
    resp = client.get("/recipes")
    assert resp.status_code == 200
    data = resp.json()
    assert [r["title"] for r in data] == ["Erdbeertorte", "Sun and Moon Cookies"]
    # summary shape, no heavy fields
    first = data[0]
    assert first["category"] == "cakes"
    assert first["tags"] == ["strawberry", "summer"]
    assert first["source"] == "import"
    assert first["rel_path"] == "cakes/erdbeertorte.md"
    assert "markdown" not in first and "sections" not in first


def test_list_filters_by_category_and_tag(client):
    assert [r["title"] for r in client.get("/recipes?category=cakes").json()] == ["Erdbeertorte"]
    assert [r["title"] for r in client.get("/recipes?tag=marzipan").json()] == [
        "Sun and Moon Cookies"
    ]
    assert client.get("/recipes?category=nope").json() == []


def test_search_matches_title_and_body(client):
    assert [r["title"] for r in client.get("/search?q=strawberry").json()] == ["Erdbeertorte"]
    assert [r["title"] for r in client.get("/search?q=cookies").json()] == ["Sun and Moon Cookies"]
    assert client.get("/search?q=zzz").json() == []


def test_search_requires_q(client):
    assert client.get("/search").status_code == 422  # missing required query param


def test_get_returns_detail_with_structure(client):
    list_resp = client.get("/recipes?category=cakes").json()
    recipe_id = list_resp[0]["id"]

    resp = client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["title"] == "Erdbeertorte"
    assert detail["markdown"].startswith("---")
    assert detail["intro"] == "A strawberry cake."
    assert [s["name"] for s in detail["sections"]] == ["Yield and timing"]


def test_get_unknown_id_404(client):
    resp = client.get("/recipes/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "recipe not found"


def test_health_does_not_require_store(tmp_path):
    # create_app() with no store must not create a DB just to answer /health
    app = create_app()
    assert TestClient(app).get("/health").json() == {"status": "ok"}
    assert app.state.store is None
