"""Tests for social-media paste import (§3.D.4): the text importer and route
validation. No live API — a fake extractor stands in for the §D.1 text call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app import main as main_mod
from _app import social_import
from _app.extraction import ExtractionUnavailable, RecipeDraft, render_markdown
from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore
from _app.web_import import ImportUnavailable

CAPTION = "Best banana bread 🍌 — 3 ripe bananas, 1 cup sugar, bake 50 min. link in bio"


class _FakeExtractor:
    def __init__(self):
        self.last = None

    def extract(self, *, text=None, image=None, source_url=None, source=None):
        self.last = {"text": text, "source": source}
        return render_markdown(
            RecipeDraft(title="Banana Bread", ingredients=["3 bananas"]), source=source
        )


# --- importer ---------------------------------------------------------------


def test_import_social_uses_text_and_stamps_source():
    fake = _FakeExtractor()
    md = social_import.import_social(CAPTION, extractor_factory=lambda: fake)
    assert "title: Banana Bread" in md
    assert "source: social" in md
    assert fake.last["source"] == "social"
    assert fake.last["text"] == CAPTION


def test_import_social_unavailable_without_key():
    def _no_llm():
        raise ExtractionUnavailable("no key")

    with pytest.raises(ImportUnavailable):
        social_import.import_social(CAPTION, extractor_factory=_no_llm)


# --- route ------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    return TestClient(create_app(store))


def test_route_social_happy_path(client, monkeypatch):
    monkeypatch.setattr(main_mod, "import_social", lambda text: f"# {text[:5]}\n")
    resp = client.post("/api/import/social", json={"text": CAPTION})
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# Best \n"


def test_route_social_empty_text_422(client):
    assert client.post("/api/import/social", json={"text": "   "}).status_code == 422


def test_route_social_unavailable_503(client, monkeypatch):
    def _raise(text):
        raise ImportUnavailable("enter by hand")

    monkeypatch.setattr(main_mod, "import_social", _raise)
    resp = client.post("/api/import/social", json={"text": CAPTION})
    assert resp.status_code == 503
    assert "enter by hand" in resp.json()["detail"]
