"""Tests for recipe image blob storage + endpoints (§3.E.1a).

Blob store points at a tmp dir (injected), so nothing touches the real _media/.
Bytes are never decoded here — that's §E.1d (export downsizing).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app.blob_store import BlobStore
from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-data" * 4

RECIPE_MD = """---
title: Lemon Loaf
category: cakes
tags: [lemon]
---
# Lemon Loaf

## Ingredients
- 1 lemon
"""


# --- blob store -------------------------------------------------------------


def test_blob_store_roundtrip_and_delete(tmp_path):
    bs = BlobStore(tmp_path)
    ref = bs.put(PNG_BYTES, "image/png")
    assert ref.endswith(".png")
    assert bs.path(ref).read_bytes() == PNG_BYTES
    assert bs.content_type(ref) == "image/png"
    bs.delete(ref)
    assert not bs.path(ref).exists()


def test_blob_store_rejects_unsupported_type(tmp_path):
    with pytest.raises(ValueError, match="unsupported"):
        BlobStore(tmp_path).put(b"x", "application/pdf")


def test_blob_store_rejects_malformed_ref(tmp_path):
    bs = BlobStore(tmp_path)
    with pytest.raises(ValueError, match="bad image ref"):
        bs.path("../etc/passwd")
    bs.delete("../etc/passwd")  # no-op, no raise


# --- endpoints --------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    blobs = BlobStore(tmp_path / "media")
    api = TestClient(create_app(store, blob_store=blobs))
    rid = api.post("/api/recipes", json={"markdown": RECIPE_MD}).json()["id"]
    return api, blobs, rid


def test_attach_serve_detach_cycle(client):
    api, blobs, rid = client

    # attach
    resp = api.post(f"/api/recipes/{rid}/images", files={"file": ("p.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 200
    urls = resp.json()["images"]
    assert len(urls) == 1 and urls[0].startswith("/api/images/")

    # detail exposes the URL
    assert api.get(f"/api/recipes/{rid}").json()["images"] == urls

    # serve returns the bytes + content-type
    served = api.get(urls[0])
    assert served.status_code == 200
    assert served.content == PNG_BYTES
    assert served.headers["content-type"] == "image/png"

    # detach removes the ref and the blob
    ref = urls[0].rsplit("/", 1)[-1]
    assert api.delete(f"/api/recipes/{rid}/images/{ref}").status_code == 204
    assert api.get(f"/api/recipes/{rid}").json()["images"] == []
    assert not blobs.path(ref).exists()


def test_attach_rejects_non_image(client):
    api, _, rid = client
    resp = api.post(f"/api/recipes/{rid}/images", files={"file": ("n.txt", b"hi", "text/plain")})
    assert resp.status_code == 415


def test_attach_oversize_413(client, monkeypatch):
    api, _, rid = client
    import _app.main as main

    monkeypatch.setattr(main, "MAX_IMAGE_BYTES", 4)
    resp = api.post(f"/api/recipes/{rid}/images", files={"file": ("p.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 413


def test_attach_unknown_recipe_404(client):
    api, _, _ = client
    resp = api.post("/api/recipes/nope/images", files={"file": ("p.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 404


def test_serve_malformed_ref_404(client):
    api, _, _ = client
    assert api.get("/api/images/not-a-valid-ref").status_code == 404


def test_delete_recipe_cleans_up_blobs(client):
    api, blobs, rid = client
    resp = api.post(f"/api/recipes/{rid}/images", files={"file": ("p.png", PNG_BYTES, "image/png")})
    ref = resp.json()["images"][0].rsplit("/", 1)[-1]
    assert blobs.path(ref).exists()

    assert api.delete(f"/api/recipes/{rid}").status_code == 204
    assert not blobs.path(ref).exists()  # blob cleaned with the recipe
