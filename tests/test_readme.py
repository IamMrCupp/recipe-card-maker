"""Render-test for `_tools/update_readme.py`.

Runs the generator against the real repo tree and asserts the structural
landmarks the rest of the workflow depends on (category headings, recipe
rows, tag cloud, setup block). This is what would catch a regression where,
say, a refactor accidentally drops a section or breaks the link format.
"""

from __future__ import annotations

from pathlib import Path

from update_readme import build_readme

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_readme_renders_without_error():
    out = build_readme(REPO_ROOT)
    assert isinstance(out, str)
    assert len(out) > 200


def test_readme_includes_h1_and_intro():
    out = build_readme(REPO_ROOT)
    assert out.startswith("# Recipes\n")
    assert "Markdown is the source of truth" in out


def test_readme_includes_category_headings_for_present_categories():
    out = build_readme(REPO_ROOT)
    # Both seed recipes are present, so both headings must appear.
    assert "## Cookies" in out
    assert "## Cakes & Tortes" in out


def test_readme_skips_empty_category_headings():
    out = build_readme(REPO_ROOT)
    # Empty categories should NOT get a heading (no recipes -> no section).
    assert "## Breads" not in out
    assert "## Pastries & Pies" not in out


def test_readme_contains_recipe_links():
    out = build_readme(REPO_ROOT)
    assert "[Sun and Moon Cookies](cookies/sun_and_moon.md)" in out
    assert "[Erdbeertorte](cakes/erdbeertorte.md)" in out


def test_readme_links_pdfs_when_present():
    # Seed recipes have both _full.pdf and _4x6.pdf committed.
    out = build_readme(REPO_ROOT)
    assert "cookies/sun_and_moon_full.pdf" in out
    assert "cookies/sun_and_moon_4x6.pdf" in out


def test_readme_tag_cloud_present():
    out = build_readme(REPO_ROOT)
    assert "## Tags" in out
    # Seed recipes share `konditorei`; it should appear with a count.
    assert "`konditorei`" in out


def test_readme_setup_block_documents_venv():
    """The B.2 venv-setup block must survive any future README-generator changes."""
    out = build_readme(REPO_ROOT)
    assert "python3 -m venv .venv" in out
    assert "pip install -r requirements.txt" in out


def test_readme_stats_line_counts_recipes():
    out = build_readme(REPO_ROOT)
    # Currently 2 seed recipes; the line is "**N recipes** across **M categories**".
    # We don't assert exact counts (will grow), just that the format is intact.
    import re

    assert re.search(r"\*\*\d+ recipes?\*\* across \*\*\d+ categories?\*\*", out)
