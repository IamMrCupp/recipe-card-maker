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

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# importing the _app package puts _tools/ on sys.path (see _app/__init__.py)
import make_cards_pdf
import make_full_pdf
from PIL import Image, ImageOps
from recipe_parser import find_recipes, parse_recipe
from update_readme import build_readme

from _app.blob_store import BlobStore
from _app.sqlite_store import REPO_ROOT, SQLiteRecipeStore
from _app.storage import Provenance, RecipeStore, StoredRecipe

# --- committed image export (§3.E.1d) --------------------------------------

_IMAGES_DIRNAME = "images"
_IMG_LONG_EDGE = 1200  # cap the long edge; web-sized, keeps the repo light
_IMG_QUALITY = 82
# Export injects a sentinel-delimited image block into the *committed* markdown so
# github.com shows photos. The sentinel makes the block exactly strippable, which
# keeps the canonical DB markdown image-free and makes re-export byte-stable.
_IMG_SENTINEL = "<!-- recipe images (managed by export — do not edit) -->"
_IMG_BLOCK_RE = re.compile(r"(?m)^" + re.escape(_IMG_SENTINEL) + r"\n(?:!\[[^\n]*\]\([^\n]*\)\n?)*")


def _strip_injected_images(markdown: str) -> str:
    """Remove an export-injected image block. No-op on canonical (image-free) md."""
    return _IMG_BLOCK_RE.sub("", markdown)


def _downsize(src: Path, dest: Path) -> None:
    """Re-encode an image to a web-sized JPEG, deterministically: EXIF orientation
    applied then dropped, no timestamps, fixed quality. Same bytes in + pinned
    Pillow => same bytes out, so committed images don't churn build-to-build."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((_IMG_LONG_EDGE, _IMG_LONG_EDGE))
        im.save(dest, "JPEG", quality=_IMG_QUALITY, optimize=True)


def _image_base(rel_path: str) -> str:
    """`cakes/erdbeertorte.md` -> `cakes-erdbeertorte` (unique across folders)."""
    return rel_path.removesuffix(".md").replace("/", "-")


def _materialize_images(stored: StoredRecipe, root: Path, blobs: BlobStore) -> list[str]:
    """Write a recipe's downsized images under root/images/. Returns committed
    image paths (posix, relative to root). Missing blobs are skipped, not fatal."""
    base = _image_base(stored.rel_path)
    single = len(stored.images) == 1
    out: list[str] = []
    for n, ref in enumerate(stored.images):
        name = f"{base}.jpg" if single else f"{base}-{n}.jpg"
        try:
            _downsize(blobs.path(ref), root / _IMAGES_DIRNAME / name)
        except (FileNotFoundError, ValueError):
            continue
        out.append(f"{_IMAGES_DIRNAME}/{name}")
    return out


def _inject_images(
    markdown: str, image_relpaths: list[str], title: str, md_dest: Path, root: Path
) -> str:
    """Insert the sentinel image block after the recipe's H1 (or append if none)."""
    if not image_relpaths:
        return markdown
    rels = [
        os.path.relpath(root / p, start=md_dest.parent).replace(os.sep, "/") for p in image_relpaths
    ]
    block = [_IMG_SENTINEL, *(f"![{title}]({r})" for r in rels)]
    lines = markdown.split("\n")
    insert_at = next((i + 1 for i, ln in enumerate(lines) if ln.startswith("# ")), len(lines))
    return "\n".join(lines[:insert_at] + block + lines[insert_at:])


def _prune_images(root: Path, referenced: set[str]) -> None:
    """Delete committed images no recipe references anymore (e.g. after a delete)."""
    images_dir = root / _IMAGES_DIRNAME
    if not images_dir.is_dir():
        return
    keep = {(root / p).resolve() for p in referenced}
    for f in images_dir.iterdir():
        if f.is_file() and f.resolve() not in keep:
            f.unlink()


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
        # Strip any export-injected image block so the canonical DB markdown stays
        # image-free (export re-injects deterministically). No-op on hand corpora.
        markdown = _strip_injected_images(path.read_text(encoding="utf-8"))
        if rel in existing:
            store.update(existing[rel].id, markdown=markdown)
            updated += 1
        else:
            store.create(markdown, source=Provenance.IMPORT, rel_path=rel)
            created += 1
    return ImportResult(created=created, updated=updated)


def export_corpus(
    store: RecipeStore,
    root: Path = REPO_ROOT,
    *,
    build: bool = True,
    blob_store: BlobStore | None = None,
) -> list[str]:
    """Write every stored recipe back to its `.md` file under `root`.

    When `build` is True, also rebuild each recipe's PDFs and regenerate the
    README — exactly what `make` does — over the materialized tree. Returns the
    list of rel_paths written. Recipes without a rel_path (not yet assigned a
    corpus location) are skipped; assigning one is the editor's job (§3.C).

    Recipe images (§3.E.1) are materialized as web-sized JPEGs under `images/`
    and referenced from the committed markdown. PDFs are built from the canonical
    markdown *before* the image block is injected, so they stay image-tag-free.
    """
    blobs = blob_store or BlobStore()

    written: list[str] = []
    for stored in store.list():
        if not stored.rel_path:
            continue
        dest = root / stored.rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(stored.markdown, encoding="utf-8")  # canonical (image-free)
        written.append(stored.rel_path)

    if build:
        for src in find_recipes(root):
            recipe = parse_recipe(src)  # reads canonical md → clean PDFs
            make_full_pdf.build_pdf(recipe, src.with_name(f"{src.stem}_full.pdf"))
            make_cards_pdf.build_pdf(recipe, src.with_name(f"{src.stem}_4x6.pdf"))
        (root / "README.md").write_text(build_readme(root), encoding="utf-8")

    # Materialize images + inject the committed-markdown image block (after PDFs).
    referenced: set[str] = set()
    for stored in store.list():
        if not stored.rel_path or not stored.images:
            continue
        dest = root / stored.rel_path
        materialized = _materialize_images(stored, root, blobs)
        referenced.update(materialized)
        if materialized:
            tagged = _inject_images(
                _strip_injected_images(stored.markdown), materialized, stored.title, dest, root
            )
            dest.write_text(tagged, encoding="utf-8")
    _prune_images(root, referenced)

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
