"""Unit tests for `_tools/recipe_parser.py`.

Covers the bits that the rest of the build (`make_full_pdf`, `make_cards_pdf`,
`update_readme`) all depend on: frontmatter parsing, section detection, list
classification, and recipe discovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from recipe_parser import (  # imported via tests/conftest.py sys.path injection
    Recipe,
    Section,
    _parse_frontmatter,
    find_recipes,
    parse_recipe,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_COOKIES = REPO_ROOT / "cookies" / "sun_and_moon.md"
SEED_CAKES = REPO_ROOT / "cakes" / "erdbeertorte.md"


# --- frontmatter parsing -----------------------------------------------------


def test_frontmatter_scalar():
    meta, body = _parse_frontmatter("---\ntitle: Foo\ndifficulty: easy\n---\nbody\n")
    assert meta["title"] == "Foo"
    assert meta["difficulty"] == "easy"
    assert body == "body\n"


def test_frontmatter_inline_list():
    meta, _ = _parse_frontmatter("---\ntags: [a, b, c]\n---\n")
    assert meta["tags"] == ["a", "b", "c"]


def test_frontmatter_empty_list():
    meta, _ = _parse_frontmatter("---\ntags: []\n---\n")
    assert meta["tags"] == []


def test_frontmatter_empty_value_is_none():
    meta, _ = _parse_frontmatter("---\nrating:\nlast_made:\n---\n")
    assert meta["rating"] is None
    assert meta["last_made"] is None


def test_frontmatter_quoted_value_stripped():
    meta, _ = _parse_frontmatter('---\nsource: "Mom"\n---\n')
    assert meta["source"] == "Mom"


def test_frontmatter_missing_returns_empty():
    meta, body = _parse_frontmatter("no frontmatter here\n")
    assert meta == {}
    assert body == "no frontmatter here\n"


# --- recipe parsing ----------------------------------------------------------


def test_parse_seed_cookies():
    r = parse_recipe(SEED_COOKIES)
    assert isinstance(r, Recipe)
    assert r.title == "Sun and Moon Cookies"
    assert r.meta["cuisine"] == "german"
    assert "marzipan" in r.meta["tags"]
    # Has the expected top-level sections
    names = [s.name for s in r.sections]
    assert "Yield and timing" in names
    assert "Mürbeteig (shortcrust base)" in names
    assert "Storage" in names


def test_parse_seed_cakes_has_components():
    r = parse_recipe(SEED_CAKES)
    biskuit = r.section("Biskuit (sponge base)")
    assert biskuit is not None
    assert "Ingredients" in biskuit.blocks
    assert "Method" in biskuit.blocks
    # Method should be a list of step strings
    method = biskuit.blocks["Method"]
    assert len(method) >= 3
    assert all(isinstance(step, str) for step in method)


def test_section_lookup_case_insensitive():
    r = parse_recipe(SEED_COOKIES)
    assert r.section("STORAGE") is not None
    assert r.section("storage") is not None
    assert r.section("Storage") is not None


def test_section_lookup_missing_returns_none():
    r = parse_recipe(SEED_COOKIES)
    assert r.section("does not exist") is None


def test_h1_title_wins_over_frontmatter():
    r = parse_recipe(SEED_COOKIES)
    # The H1 ("# Sun and Moon Cookies") should be used as the title
    # even though frontmatter also has a title field.
    assert r.title == "Sun and Moon Cookies"


# --- find_recipes ------------------------------------------------------------


def test_find_recipes_returns_seed_recipes():
    found = find_recipes(REPO_ROOT)
    assert SEED_COOKIES in found
    assert SEED_CAKES in found


def test_find_recipes_skips_underscore_dirs():
    # _templates/recipe_full.md exists but must NOT be discovered.
    found = find_recipes(REPO_ROOT)
    template = REPO_ROOT / "_templates" / "recipe_full.md"
    assert template.exists()
    assert template not in found


def test_find_recipes_skips_readme():
    found = find_recipes(REPO_ROOT)
    readme = REPO_ROOT / "README.md"
    assert readme.exists()
    assert readme not in found


# --- section body classification --------------------------------------------


def test_method_section_parses_as_numbered_steps(tmp_path):
    md = tmp_path / "r.md"
    md.write_text(
        "---\ntitle: T\n---\n# T\n\n## Step section\n\n### Method\n\n1. First.\n2. Second.\n",
        encoding="utf-8",
    )
    r = parse_recipe(md)
    s = r.section("Step section")
    assert s is not None
    assert s.blocks["Method"] == ["First.", "Second."]


def test_ingredients_section_parses_as_bullets(tmp_path):
    md = tmp_path / "r.md"
    md.write_text(
        "---\ntitle: T\n---\n# T\n\n## Comp\n\n### Ingredients\n\n- 100 g flour\n- 1 egg\n",
        encoding="utf-8",
    )
    r = parse_recipe(md)
    s = r.section("Comp")
    assert s.blocks["Ingredients"] == ["100 g flour", "1 egg"]


def test_section_with_no_subsections_falls_back_to_prose(tmp_path):
    md = tmp_path / "r.md"
    md.write_text(
        "---\ntitle: T\n---\n# T\n\n## Notes\n\n"
        "A free-form note paragraph.\n\nAnother paragraph.\n",
        encoding="utf-8",
    )
    r = parse_recipe(md)
    s = r.section("Notes")
    assert s.blocks == {}
    assert len(s.prose) == 2


def test_section_dataclass_defaults():
    s = Section(name="X")
    assert s.intro == ""
    assert s.blocks == {}
    assert s.prose == []


# --- regression: rating field type tolerance (the parser shouldn't crash) ----


def test_recipes_with_no_rating_parse_cleanly():
    # Both seed recipes have empty `rating:` — make sure parse_recipe doesn't choke.
    parse_recipe(SEED_COOKIES)
    parse_recipe(SEED_CAKES)


# Run smoke: every recipe under the repo parses without raising.
def test_all_repo_recipes_parse():
    for p in find_recipes(REPO_ROOT):
        r = parse_recipe(p)
        assert r.title, f"empty title for {p}"
        assert r.sections, f"no sections for {p}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
