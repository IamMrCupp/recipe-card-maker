"""Tests for the write API (§3.C.1): create / update / delete.

The write path is markdown-based and has no LLM/network dependency — hand entry
is the always-available baseline.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore

CAKE_MD = """---
title: Erdbeertorte
category: cakes
tags: [strawberry]
---
# Erdbeertorte

## Yield and timing
- 8 servings
"""


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    return TestClient(create_app(store)), store


def test_create_returns_201_and_detail(client):
    api, _ = client
    resp = api.post("/api/recipes", json={"markdown": CAKE_MD})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Erdbeertorte"
    assert body["source"] == "hand"  # default provenance
    assert body["rel_path"] == "cakes/erdbeertorte.md"  # derived from category + slug
    assert body["id"]


def test_create_is_fetchable_and_listed(client):
    api, _ = client
    rid = api.post("/api/recipes", json={"markdown": CAKE_MD}).json()["id"]
    assert api.get(f"/api/recipes/{rid}").status_code == 200
    assert [r["title"] for r in api.get("/api/recipes").json()] == ["Erdbeertorte"]


def test_create_explicit_category_overrides_frontmatter(client):
    api, _ = client
    body = api.post("/api/recipes", json={"markdown": CAKE_MD, "category": "desserts"}).json()
    assert body["rel_path"] == "desserts/erdbeertorte.md"


def test_create_uncategorized_has_no_rel_path(client):
    api, _ = client
    md = "# Plain Cake\n\n## Yield\n- 1"  # no category anywhere
    body = api.post("/api/recipes", json={"markdown": md}).json()
    assert body["rel_path"] is None


def test_create_rejects_empty_and_titleless(client):
    api, _ = client
    assert api.post("/api/recipes", json={"markdown": "   "}).status_code == 422
    assert api.post("/api/recipes", json={"markdown": "- just a bullet"}).status_code == 422


def test_create_with_provenance(client):
    api, _ = client
    body = api.post("/api/recipes", json={"markdown": CAKE_MD, "source": "website"}).json()
    assert body["source"] == "website"


def test_update_changes_content(client):
    api, _ = client
    rid = api.post("/api/recipes", json={"markdown": CAKE_MD}).json()["id"]
    edited = CAKE_MD.replace("8 servings", "10 servings")
    resp = api.put(f"/api/recipes/{rid}", json={"markdown": edited})
    assert resp.status_code == 200
    assert "10 servings" in resp.json()["markdown"]
    assert "10 servings" in api.get(f"/api/recipes/{rid}").json()["markdown"]


def test_update_rejects_invalid_and_missing(client):
    api, _ = client
    rid = api.post("/api/recipes", json={"markdown": CAKE_MD}).json()["id"]
    assert api.put(f"/api/recipes/{rid}", json={"markdown": ""}).status_code == 422
    assert api.put("/api/recipes/nope", json={"markdown": CAKE_MD}).status_code == 404


def test_delete(client):
    api, _ = client
    rid = api.post("/api/recipes", json={"markdown": CAKE_MD}).json()["id"]
    assert api.delete(f"/api/recipes/{rid}").status_code == 204
    assert api.get(f"/api/recipes/{rid}").status_code == 404
    assert api.delete(f"/api/recipes/{rid}").status_code == 404


def test_created_recipe_exports_to_its_rel_path(client, tmp_path):
    # A hand-created recipe with a category round-trips through export to a file.
    from _app.corpus import export_corpus

    api, store = client
    api.post("/api/recipes", json={"markdown": CAKE_MD})
    out_root = tmp_path / "out"
    out_root.mkdir()
    written = export_corpus(store, out_root, build=False)
    assert "cakes/erdbeertorte.md" in written
    assert (out_root / "cakes" / "erdbeertorte.md").read_text(encoding="utf-8") == CAKE_MD
