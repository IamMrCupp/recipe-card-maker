"""Tests for serving the SvelteKit SPA from FastAPI (§3.B.2).

Uses a fake build dir so the behavior is verified without a real frontend build.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore


@pytest.fixture
def build_dir(tmp_path):
    d = tmp_path / "build"
    (d / "_app").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>Recipe Box</title>", encoding="utf-8")
    (d / "_app" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (d / "manifest.webmanifest").write_text('{"name":"Recipe Box"}', encoding="utf-8")
    return d


@pytest.fixture
def client(tmp_path, build_dir):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    return TestClient(create_app(store, web_build_dir=build_dir))


def test_root_serves_index_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Recipe Box" in resp.text


def test_real_asset_is_served(client):
    resp = client.get("/_app/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_client_route_falls_back_to_index(client):
    # A deep client-side route (no such file) must serve the SPA shell, not 404.
    resp = client.get("/recipes/some-id")
    assert resp.status_code == 200
    assert "Recipe Box" in resp.text


def test_api_takes_precedence_over_spa(client):
    # /api/recipes is the JSON API, not the SPA fallback.
    resp = client.get("/api/recipes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_api_path_is_404_not_spa(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert "<title>" not in resp.text  # not the SPA shell


def test_health_still_works_with_spa(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_api_only_mode_when_no_build(tmp_path):
    # No build dir → API works, but unknown routes are a plain 404 (no SPA fallback).
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    app_client = TestClient(create_app(store, web_build_dir=tmp_path / "missing"))
    assert app_client.get("/api/recipes").status_code == 200
    assert app_client.get("/recipes/some-id").status_code == 404
