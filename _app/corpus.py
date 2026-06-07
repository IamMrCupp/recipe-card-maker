"""Markdown ⇄ DB adapters (Phase 3 §3.A.3).

The bridge between the portable markdown corpus and the database store:

  * **import_corpus** — walk the recipe tree, upsert each file into the store
    (keyed by its corpus-relative path, so re-running is idempotent).
  * **export_corpus** — write every stored recipe back to its `.md` file, then
    rebuild the PDFs + README via the existing build tooling.

This is built early and deliberately (not last): it's the regression net that
proves the data-truth flip lost nothing — `import` then `export` reproduces the
committed corpus byte-for-byte. It also keeps a portable, human-readable backup
of the truth and the GitHub-browsable view current.

CLI:  python -m _app.corpus import   |   python -m _app.corpus export
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# importing the _app package puts _tools/ on sys.path (see _app/__init__.py)
import make_cards_pdf
import make_full_pdf
from recipe_parser import find_recipes, parse_recipe
from update_readme import build_readme

from _app.sqlite_store import REPO_ROOT, SQLiteRecipeStore
from _app.storage import Provenance, RecipeStore


@dataclass
class ImportResult:
    created: int
    updated: int

    @property
    def total(self) -> int:
        return self.created + self.updated


def import_corpus(store: RecipeStore, root: Path = REPO_ROOT) -> ImportResult:
    """Upsert every recipe file under `root` into the store, keyed by rel_path.

    Idempotent: a file already present (same rel_path) is updated in place
    rather than duplicated.
    """
    existing = {s.rel_path: s for s in store.list() if s.rel_path}
    created = updated = 0
    for path in find_recipes(root):
        rel = path.relative_to(root).as_posix()
        markdown = path.read_text(encoding="utf-8")
        if rel in existing:
            store.update(existing[rel].id, markdown=markdown)
            updated += 1
        else:
            store.create(markdown, source=Provenance.IMPORT, rel_path=rel)
            created += 1
    return ImportResult(created=created, updated=updated)


def export_corpus(store: RecipeStore, root: Path = REPO_ROOT, *, build: bool = True) -> list[str]:
    """Write every stored recipe back to its `.md` file under `root`.

    When `build` is True, also rebuild each recipe's PDFs and regenerate the
    README — exactly what `make` does — over the materialized tree. Returns the
    list of rel_paths written. Recipes without a rel_path (not yet assigned a
    corpus location) are skipped; assigning one is the editor's job (§3.C).
    """
    written: list[str] = []
    for stored in store.list():
        if not stored.rel_path:
            continue
        dest = root / stored.rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(stored.markdown, encoding="utf-8")
        written.append(stored.rel_path)

    if build:
        for src in find_recipes(root):
            recipe = parse_recipe(src)
            make_full_pdf.build_pdf(recipe, src.with_name(f"{src.stem}_full.pdf"))
            make_cards_pdf.build_pdf(recipe, src.with_name(f"{src.stem}_4x6.pdf"))
        (root / "README.md").write_text(build_readme(root), encoding="utf-8")

    return written


def _main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in {"import", "export"}:
        print("usage: python -m _app.corpus {import|export}", file=sys.stderr)
        return 2
    store = SQLiteRecipeStore()
    if argv[0] == "import":
        result = import_corpus(store)
        print(f"imported: {result.created} created, {result.updated} updated")
    else:
        written = export_corpus(store)
        print(f"exported: {len(written)} recipe(s) + README + PDFs")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
