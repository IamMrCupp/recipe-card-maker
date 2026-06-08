"""Tests for committed image export (§3.E.1d).

Export materializes a recipe's images as web-sized JPEGs under images/ and
injects a sentinel-delimited block into the committed markdown — without touching
the canonical DB markdown, deterministically (byte-stable), and round-trip-safe
(import strips the block so re-export reproduces it exactly).

`build=False` skips PDF/README generation; image handling runs regardless.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from _app import corpus
from _app.blob_store import BlobStore
from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import Provenance

RECIPE_MD = """---
title: Lemon Loaf
category: cakes
tags: [lemon]
---
# Lemon Loaf

A bright loaf.

## Ingredients
- 1 lemon
"""


def _png_bytes(color=(200, 50, 50), size=(1800, 1400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path):
    blobs = BlobStore(tmp_path / "media")
    ref = blobs.put(_png_bytes(), "image/png")
    store = SQLiteRecipeStore(db_path=tmp_path / "x.db")
    stored = store.create(
        RECIPE_MD, source=Provenance.HAND, rel_path="cakes/lemon.md", images=[ref]
    )
    root = tmp_path / "root"
    root.mkdir()
    return store, blobs, root, stored.id, ref


def test_export_materializes_and_references(env):
    store, blobs, root, _, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)

    img = root / "images" / "cakes-lemon.jpg"
    assert img.exists()
    # downsized: long edge capped at 1200
    assert max(Image.open(img).size) <= 1200

    md = (root / "cakes" / "lemon.md").read_text()
    assert corpus._IMG_SENTINEL in md
    assert "![Lemon Loaf](../images/cakes-lemon.jpg)" in md
    # injected right after the H1
    assert "# Lemon Loaf\n" + corpus._IMG_SENTINEL in md


def test_export_is_byte_deterministic(env):
    store, blobs, root, _, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    img1 = (root / "images" / "cakes-lemon.jpg").read_bytes()
    md1 = (root / "cakes" / "lemon.md").read_bytes()

    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    assert (root / "images" / "cakes-lemon.jpg").read_bytes() == img1  # re-encode stable
    assert (root / "cakes" / "lemon.md").read_bytes() == md1  # no double-injection


def test_canonical_db_markdown_untouched(env):
    store, blobs, root, rid, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    db_md = store.get(rid).markdown
    assert corpus._IMG_SENTINEL not in db_md
    assert "images/" not in db_md


def test_import_strips_injected_block(env):
    store, blobs, root, _, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    # a fresh store importing the exported (tagged) tree keeps canonical md clean
    store2 = SQLiteRecipeStore(db_path=root.parent / "y.db")
    corpus.import_corpus(store2, root=root)
    imported = next(s for s in store2.list() if s.rel_path == "cakes/lemon.md")
    assert corpus._IMG_SENTINEL not in imported.markdown
    assert imported.markdown.rstrip() == RECIPE_MD.rstrip()


def test_export_import_export_is_stable(env):
    store, blobs, root, _, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    md1 = (root / "cakes" / "lemon.md").read_bytes()
    img1 = (root / "images" / "cakes-lemon.jpg").read_bytes()

    # round-trip the committed tree through a fresh store, carrying the image ref
    store2 = SQLiteRecipeStore(db_path=root.parent / "z.db")
    corpus.import_corpus(store2, root=root)
    rid2 = next(s for s in store2.list() if s.rel_path == "cakes/lemon.md").id
    new_ref = blobs.put(_png_bytes(), "image/png")  # re-attach an equivalent image
    store2.update(rid2, images=[new_ref])

    corpus.export_corpus(store2, root=root, build=False, blob_store=blobs)
    assert (root / "cakes" / "lemon.md").read_bytes() == md1
    assert (root / "images" / "cakes-lemon.jpg").read_bytes() == img1


def test_orphan_images_pruned(env):
    store, blobs, root, rid, _ = env
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    assert (root / "images" / "cakes-lemon.jpg").exists()

    store.update(rid, images=[])  # detach the image
    corpus.export_corpus(store, root=root, build=False, blob_store=blobs)
    assert not (root / "images" / "cakes-lemon.jpg").exists()  # pruned
    md = (root / "cakes" / "lemon.md").read_text()
    assert corpus._IMG_SENTINEL not in md  # block gone too
