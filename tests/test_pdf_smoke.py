"""Smoke + determinism tests for the PDF builders.

Builds PDFs from the seed recipes into a tmp dir and verifies:
- the output looks like a real PDF (magic bytes + non-trivial size)
- two consecutive builds are byte-identical (the §1.B.3 determinism guarantee
  that §1.E will rely on for byte-comparison of the dedup refactor)
"""

from __future__ import annotations

from pathlib import Path

import make_cards_pdf
import make_full_pdf
import pytest
from recipe_parser import parse_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_RECIPES = [
    REPO_ROOT / "cookies" / "sun_and_moon.md",
    REPO_ROOT / "cakes" / "erdbeertorte.md",
]


@pytest.fixture(params=SEED_RECIPES, ids=lambda p: p.stem)
def recipe_path(request):
    return request.param


# --- full-page (letter) PDFs -------------------------------------------------


def test_full_pdf_builds_and_looks_like_pdf(recipe_path, tmp_path):
    out = tmp_path / f"{recipe_path.stem}_full.pdf"
    make_full_pdf.build_pdf(parse_recipe(recipe_path), out)
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"%PDF-"), "missing PDF magic bytes"
    assert data.rstrip().endswith(b"%%EOF"), "missing PDF trailer"
    assert len(data) > 1000, "suspiciously small PDF"


def test_full_pdf_is_deterministic(recipe_path, tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    make_full_pdf.build_pdf(parse_recipe(recipe_path), a)
    make_full_pdf.build_pdf(parse_recipe(recipe_path), b)
    assert a.read_bytes() == b.read_bytes(), "consecutive builds differ — determinism broken"


# --- 4x6 card PDFs -----------------------------------------------------------


def test_cards_pdf_builds_and_looks_like_pdf(recipe_path, tmp_path):
    out = tmp_path / f"{recipe_path.stem}_4x6.pdf"
    make_cards_pdf.build_pdf(parse_recipe(recipe_path), out)
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"%PDF-")
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 1000


def test_cards_pdf_is_deterministic(recipe_path, tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    make_cards_pdf.build_pdf(parse_recipe(recipe_path), a)
    make_cards_pdf.build_pdf(parse_recipe(recipe_path), b)
    assert a.read_bytes() == b.read_bytes(), "consecutive builds differ — determinism broken"


# --- the deterministic-date pin really takes effect -------------------------


def test_full_pdf_embeds_pinned_creation_date(tmp_path):
    """Sanity check that SOURCE_DATE_EPOCH pinning is wired through to ReportLab."""
    out = tmp_path / "x.pdf"
    make_full_pdf.build_pdf(parse_recipe(SEED_RECIPES[0]), out)
    data = out.read_bytes()
    # _buildmeta pins SOURCE_DATE_EPOCH = 1704067200 → 2024-01-01T00:00:00Z
    # ReportLab writes that as /CreationDate (D:20240101000000+00'00')
    assert b"D:20240101000000" in data, "PDF date pin not embedded — _buildmeta not in effect"
