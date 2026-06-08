"""Tests for photo import (§3.D.3): the vision-path importer, route validation
(content-type / size / availability), and the capabilities endpoint.

No live API: a fake extractor stands in for the §D.1 Claude vision call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app import main as main_mod
from _app import photo_import
from _app.extraction import ExtractionUnavailable, RecipeDraft, render_markdown
from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore
from _app.web_import import ImportUnavailable

TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # not a real image; bytes are never decoded here


class _FakeExtractor:
    def __init__(self):
        self.last = None

    def extract(self, *, text=None, image=None, source_url=None, source=None):
        self.last = {"image": image, "source": source}
        return render_markdown(
            RecipeDraft(title="From Photo", ingredients=["1 egg"]), source=source
        )


# --- importer ---------------------------------------------------------------


def test_import_photo_uses_vision_and_stamps_source():
    fake = _FakeExtractor()
    md = photo_import.import_photo(TINY_PNG, "image/png", extractor_factory=lambda: fake)
    assert "title: From Photo" in md
    assert "source: photo" in md
    assert fake.last["source"] == "photo"
    assert fake.last["image"].media_type == "image/png"
    assert fake.last["image"].data == TINY_PNG


def test_import_photo_unavailable_without_key():
    def _no_llm():
        raise ExtractionUnavailable("no key")

    with pytest.raises(ImportUnavailable):
        photo_import.import_photo(TINY_PNG, "image/png", extractor_factory=_no_llm)


# --- route + capabilities ---------------------------------------------------


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    return TestClient(create_app(store))


def test_route_photo_happy_path(client, monkeypatch):
    monkeypatch.setattr(main_mod, "import_photo", lambda data, mt: f"# from {mt}\n")
    resp = client.post("/api/import/photo", files={"file": ("r.jpg", TINY_PNG, "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# from image/jpeg\n"


def test_route_photo_rejects_non_image(client):
    resp = client.post("/api/import/photo", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 415


def test_route_photo_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(main_mod, "MAX_IMAGE_BYTES", 4)
    resp = client.post(
        "/api/import/photo", files={"file": ("r.png", b"larger than four", "image/png")}
    )
    assert resp.status_code == 413


def test_route_photo_unavailable_503(client, monkeypatch):
    def _raise(data, mt):
        raise ImportUnavailable("enter by hand")

    monkeypatch.setattr(main_mod, "import_photo", _raise)
    resp = client.post("/api/import/photo", files={"file": ("r.png", TINY_PNG, "image/png")})
    assert resp.status_code == 503
    assert "enter by hand" in resp.json()["detail"]


@pytest.mark.parametrize("flag", [True, False])
def test_capabilities_reflects_extraction_available(client, monkeypatch, flag):
    monkeypatch.setattr(main_mod, "extraction_available", lambda: flag)
    resp = client.get("/api/import/capabilities")
    assert resp.status_code == 200
    assert resp.json() == {"llm_extraction": flag}
