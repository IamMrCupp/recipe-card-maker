"""Regenerate README.md from the recipe collection.

Walks the tree, reads frontmatter from every recipe, and builds:
  - a categorized index with links to markdown + PDFs
  - a quick stats summary
  - a tags section

Usage:
    python _tools/update_readme.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe_parser import find_recipes, parse_recipe  # noqa: E402


CATEGORY_ORDER = [
    "cookies",
    "cakes",
    "breads",
    "pastries",
    "custards_and_creams",
    "confections",
    "savory",
    "drinks",
]

CATEGORY_TITLES = {
    "cookies": "Cookies",
    "cakes": "Cakes & Tortes",
    "breads": "Breads",
    "pastries": "Pastries & Pies",
    "custards_and_creams": "Custards & Creams",
    "confections": "Confections",
    "savory": "Savory",
    "drinks": "Drinks",
}


def _category_of(recipe_path: Path, root: Path) -> str:
    """First path component under root is the category."""
    rel = recipe_path.relative_to(root)
    return rel.parts[0]


def _relative_href(target: Path, root: Path) -> str:
    """Path relative to repo root, posix-style, for README links."""
    return target.relative_to(root).as_posix()


def _format_row(recipe, root: Path) -> str:
    """One row of the recipe table."""
    md_rel = _relative_href(recipe.source_path, root)
    slug = recipe.source_path.stem
    folder = recipe.source_path.parent

    pdf_full = folder / f"{slug}_full.pdf"
    pdf_4x6 = folder / f"{slug}_4x6.pdf"

    pdf_links = []
    if pdf_full.exists():
        pdf_links.append(f"[letter]({_relative_href(pdf_full, root)})")
    if pdf_4x6.exists():
        pdf_links.append(f"[4×6]({_relative_href(pdf_4x6, root)})")
    pdf_cell = " · ".join(pdf_links) if pdf_links else "—"

    cuisine = recipe.meta.get("cuisine") or "—"
    if cuisine != "—":
        cuisine = cuisine.replace("_", " ").title()

    difficulty = recipe.meta.get("difficulty") or "—"
    active = recipe.meta.get("active_time") or "—"

    rating_val = recipe.meta.get("rating")
    if rating_val:
        try:
            n = int(str(rating_val).strip())
            rating = "★" * n + "☆" * (5 - n)
        except (ValueError, TypeError):
            rating = str(rating_val)
    else:
        rating = "—"

    return (
        f"| [{recipe.title}]({md_rel}) "
        f"| {cuisine} "
        f"| {difficulty} "
        f"| {active} "
        f"| {rating} "
        f"| {pdf_cell} |"
    )


def _table_header() -> list[str]:
    return [
        "| Recipe | Cuisine | Difficulty | Active time | Rating | PDFs |",
        "| --- | --- | --- | --- | --- | --- |",
    ]


def build_readme(root: Path) -> str:
    recipes = [parse_recipe(p) for p in find_recipes(root)]

    by_category: dict[str, list] = defaultdict(list)
    for r in recipes:
        by_category[_category_of(r.source_path, root)].append(r)
    for cat in by_category:
        by_category[cat].sort(key=lambda r: r.title.lower())

    # Tag frequency
    tag_counter: Counter[str] = Counter()
    for r in recipes:
        for t in r.meta.get("tags") or []:
            tag_counter[t] += 1

    lines: list[str] = []

    # ---- Header ----
    lines.append("# Recipes")
    lines.append("")
    lines.append(
        "A personal recipe collection. Markdown is the source of truth; PDFs "
        "(full-page letter for kitchen binders, 4×6 for the recipe tin) are "
        "generated artifacts."
    )
    lines.append("")
    lines.append(
        f"**{len(recipes)} recipes** across **{len(by_category)} categories** "
        f"· last built {date.today().isoformat()}"
    )
    lines.append("")

    # ---- Quick links ----
    lines.append("## Quick links")
    lines.append("")
    for cat in CATEGORY_ORDER:
        if cat in by_category:
            title = CATEGORY_TITLES.get(cat, cat.title())
            anchor = title.lower().replace(" & ", "--").replace(" ", "-")
            lines.append(f"- [{title}](#{anchor}) ({len(by_category[cat])})")
    lines.append("")

    # ---- Per-category tables ----
    for cat in CATEGORY_ORDER:
        if cat not in by_category:
            continue
        title = CATEGORY_TITLES.get(cat, cat.title())
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(_table_header())
        for r in by_category[cat]:
            lines.append(_format_row(r, root))
        lines.append("")

    # Any category we didn't list explicitly
    unknown = set(by_category) - set(CATEGORY_ORDER)
    for cat in sorted(unknown):
        lines.append(f"## {cat.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(_table_header())
        for r in by_category[cat]:
            lines.append(_format_row(r, root))
        lines.append("")

    # ---- Tags ----
    if tag_counter:
        lines.append("## Tags")
        lines.append("")
        tag_line = " · ".join(
            f"`{tag}` ({n})" for tag, n in tag_counter.most_common()
        )
        lines.append(tag_line)
        lines.append("")

    # ---- Usage footer ----
    lines.append("## Working with this repo")
    lines.append("")
    lines.append(
        "First-time setup (needs Python 3.14 — see `.python-version`). "
        "Create a virtualenv and install the pinned dependencies:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append("python3 -m venv .venv")
    lines.append("source .venv/bin/activate")
    lines.append("pip install -r requirements.txt")
    lines.append("```")
    lines.append("")
    lines.append("Then, with the venv active:")
    lines.append("")
    lines.append("```bash")
    lines.append("# rebuild all PDFs")
    lines.append("make")
    lines.append("")
    lines.append("# rebuild just one recipe")
    lines.append("python _tools/make_full_pdf.py cookies/sun_and_moon.md")
    lines.append("python _tools/make_cards_pdf.py cookies/sun_and_moon.md")
    lines.append("")
    lines.append("# regenerate this README")
    lines.append("python _tools/update_readme.py")
    lines.append("```")
    lines.append("")
    lines.append(
        "To add a new recipe, copy `_templates/recipe_full.md` into the "
        "appropriate category folder, fill in the frontmatter and body, "
        "then `make`."
    )
    lines.append("")

    return "\n".join(lines)


def main():
    root = Path(__file__).resolve().parent.parent
    readme = build_readme(root)
    (root / "README.md").write_text(readme, encoding="utf-8")
    print(f"  wrote README.md ({len(readme)} chars)")


if __name__ == "__main__":
    main()
