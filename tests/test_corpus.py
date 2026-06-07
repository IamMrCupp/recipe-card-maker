"""Tests for the markdown ⇄ DB adapters (_app/corpus.py).

Phase 3 §3.A.3. The headline guarantee: importing the real corpus and exporting
it straight back reproduces every recipe `.md` byte-for-byte — the regression
net that proves the data-truth flip lost nothing. These tests never mutate the
real repo: they import from REPO_ROOT (read-only) and export into tmp dirs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from recipe_parser import find_recipes

from _app.corpus import export_corpus, import_corpus
from _app.sqlite_store import REPO_ROOT, SQLiteRecipeStore

CAKE_MD = """---
title: Erdbeertorte
category: cakes
tags: [strawberry, summer]
---
# Erdbeertorte

## Yield and timing
- 8 servings
"""

COOKIE_MD = """---
title: Sun and Moon Cookies
category: cookies
---
# Sun and Moon Cookies

## Yield and timing
- 24 cookies
"""


@pytest.fixture
def store(tmp_path):
    return SQLiteRecipeStore(db_path=tmp_path / "test.db")


def _make_corpus(root: Path) -> None:
    (root / "cakes").mkdir()
    (root / "cookies").mkdir()
    (root / "cakes" / "erdbeertorte.md").write_text(CAKE_MD, encoding="utf-8")
    (root / "cookies" / "sun_and_moon.md").write_text(COOKIE_MD, encoding="utf-8")


def test_import_then_export_reproduces_files_byte_identical(store, tmp_path):
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_corpus(src_root)

    result = import_corpus(store, src_root)
    assert result.created == 2
    assert result.updated == 0

    out_root = tmp_path / "out"
    out_root.mkdir()
    written = export_corpus(store, out_root, build=False)
    assert sorted(written) == ["cakes/erdbeertorte.md", "cookies/sun_and_moon.md"]

    # byte-for-byte identical, including the original filename (not a slug)
    assert (out_root / "cakes" / "erdbeertorte.md").read_bytes() == CAKE_MD.encode()
    assert (out_root / "cookies" / "sun_and_moon.md").read_bytes() == COOKIE_MD.encode()


def test_import_is_idempotent(store, tmp_path):
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_corpus(src_root)

    first = import_corpus(store, src_root)
    second = import_corpus(store, src_root)

    assert first.created == 2
    assert second.created == 0
    assert second.updated == 2
    assert len(store.list()) == 2  # no duplicates


def test_import_picks_up_content_changes(store, tmp_path):
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_corpus(src_root)
    import_corpus(store, src_root)

    edited = CAKE_MD.replace("8 servings", "10 servings")
    (src_root / "cakes" / "erdbeertorte.md").write_text(edited, encoding="utf-8")
    import_corpus(store, src_root)

    cake = next(s for s in store.list() if s.rel_path == "cakes/erdbeertorte.md")
    assert "10 servings" in cake.markdown


def test_export_with_build_creates_pdfs_and_readme(store, tmp_path):
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_corpus(src_root)
    import_corpus(store, src_root)

    out_root = tmp_path / "out"
    out_root.mkdir()
    export_corpus(store, out_root, build=True)

    assert (out_root / "README.md").exists()
    assert (out_root / "cakes" / "erdbeertorte_full.pdf").exists()
    assert (out_root / "cakes" / "erdbeertorte_4x6.pdf").exists()
    assert (out_root / "README.md").read_text(encoding="utf-8").startswith("#")


def test_export_readme_is_deterministic(store, tmp_path):
    """A second export reproduces the README byte-for-byte (no live date stamp)."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_corpus(src_root)
    import_corpus(store, src_root)

    out_root = tmp_path / "out"
    out_root.mkdir()
    export_corpus(store, out_root, build=True)
    first = (out_root / "README.md").read_bytes()
    export_corpus(store, out_root, build=True)
    second = (out_root / "README.md").read_bytes()
    assert first == second


def test_real_corpus_round_trips_byte_identical(store, tmp_path):
    """Import the actual repo corpus and export it elsewhere — every file matches."""
    import_corpus(store, REPO_ROOT)
    out_root = tmp_path / "real_out"
    out_root.mkdir()
    export_corpus(store, out_root, build=False)

    originals = find_recipes(REPO_ROOT)
    assert originals, "expected at least one real recipe in the repo"
    for original in originals:
        rel = original.relative_to(REPO_ROOT)
        assert (out_root / rel).read_bytes() == original.read_bytes(), f"mismatch: {rel}"
