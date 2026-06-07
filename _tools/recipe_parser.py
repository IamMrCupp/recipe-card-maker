"""Parse recipe markdown files with YAML frontmatter into structured data.

Recipe markdown schema:
    ---
    title: ...
    category: ...
    ...yaml frontmatter...
    ---

    # Title

    Optional intro paragraph(s).

    ## Yield and timing      <- parsed specially
    - bullet
    - bullet

    ## Section name          <- becomes a component
    ### Ingredients          <- bullets = ingredient list
    - 250 g flour
    ### Method               <- numbered list = steps
    1. Do the thing.
    2. Do the next thing.

    ## Section with no subsections
    <free-form content>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Section:
    """A top-level (##) section of a recipe.

    Subsections (###) like 'Ingredients' and 'Method' are captured as
    named block lists in `blocks`. Everything else falls into `prose`.
    """

    name: str
    intro: str = ""  # text between ## and first ### (or next ##)
    blocks: dict[str, list[str]] = field(default_factory=dict)
    prose: list[str] = field(default_factory=list)  # free-form paragraphs when no ### subsections


@dataclass
class Recipe:
    meta: dict[str, Any]
    title: str
    intro: str  # paragraphs between # title and first ##
    sections: list[Section]
    source_path: Path | None  # None for recipes parsed from in-memory text (e.g. the DB)

    @property
    def slug(self) -> str:
        if self.source_path is not None:
            return self.source_path.stem
        # Path-less recipe (DB-origin): derive a slug from the title.
        return re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_") or "untitled"

    def section(self, name: str) -> Section | None:
        """Case-insensitive lookup of a section by name."""
        low = name.lower()
        for s in self.sections:
            if s.name.lower() == low:
                return s
        return None


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML-ish frontmatter parser.

    Supports: scalar values, inline lists [a, b, c], and ignores empty values.
    We avoid a PyYAML dep because the schema is simple and under our control.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    body = text[m.end() :]
    meta: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()

        if raw == "":
            meta[key] = None
        elif raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            meta[key] = [item.strip() for item in inner.split(",") if item.strip()] if inner else []
        else:
            # strip surrounding quotes if present
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1]
            meta[key] = raw
    return meta, body


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------


def _strip_bullet(line: str) -> str | None:
    """Return text if line is a '- ' bullet, else None."""
    m = re.match(r"^\s*[-*]\s+(.*)$", line)
    return m.group(1).strip() if m else None


def _strip_numbered(line: str) -> str | None:
    """Return text if line is a '1. ' numbered item, else None."""
    m = re.match(r"^\s*\d+\.\s+(.*)$", line)
    return m.group(1).strip() if m else None


def _collect_paragraphs(lines: list[str]) -> list[str]:
    """Group consecutive non-empty lines into paragraphs, preserving list items verbatim."""
    paragraphs: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            paragraphs.append(" ".join(x.strip() for x in buf).strip())
            buf.clear()

    for line in lines:
        if not line.strip():
            flush()
        elif _strip_bullet(line) is not None or _strip_numbered(line) is not None:
            flush()
            paragraphs.append(line.strip())
        else:
            buf.append(line)
    flush()
    return [p for p in paragraphs if p]


def _collect_list_items(lines: list[str], kind: str) -> list[str]:
    """Collect either bullet or numbered items, merging continuation lines."""
    strip = _strip_bullet if kind == "bullet" else _strip_numbered
    items: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            items.append(" ".join(x.strip() for x in current).strip())
            current.clear()

    for line in lines:
        stripped = strip(line)
        if stripped is not None:
            flush()
            current.append(stripped)
        elif line.strip() and current:
            # continuation of the previous list item (indented wrap)
            current.append(line.strip())
        elif not line.strip():
            # blank line doesn't break a list, but ends the current item
            # for our purposes (items are always single logical items here)
            flush()
    flush()
    return items


def _parse_section_body(body_lines: list[str]) -> tuple[str, dict[str, list[str]], list[str]]:
    """Parse the body of a ## section: find ### subsections, else treat as prose."""
    # Split on ### subsection headers
    sub_re = re.compile(r"^###\s+(.+?)\s*$")

    intro_lines: list[str] = []
    subs: list[tuple[str, list[str]]] = []
    current_sub: tuple[str, list[str]] | None = None

    for line in body_lines:
        m = sub_re.match(line)
        if m:
            if current_sub:
                subs.append(current_sub)
            current_sub = (m.group(1).strip(), [])
        else:
            if current_sub:
                current_sub[1].append(line)
            else:
                intro_lines.append(line)
    if current_sub:
        subs.append(current_sub)

    intro = "\n".join(intro_lines).strip()

    # If we have named subsections, classify each:
    #   - bullet lists -> list items
    #   - numbered lists -> numbered items (still store as list[str])
    #   - mixed / prose -> paragraphs
    blocks: dict[str, list[str]] = {}
    for name, sub_lines in subs:
        # detect the dominant list type
        bullet_items = _collect_list_items(sub_lines, "bullet")
        numbered_items = _collect_list_items(sub_lines, "numbered")
        if numbered_items and len(numbered_items) >= len(bullet_items):
            blocks[name] = numbered_items
        elif bullet_items:
            blocks[name] = bullet_items
        else:
            blocks[name] = _collect_paragraphs(sub_lines)

    # If no subsections, collect everything as prose paragraphs
    prose: list[str] = []
    if not blocks:
        prose = _collect_paragraphs(intro_lines)
        intro = ""

    return intro, blocks, prose


def parse_recipe_text(text: str, source_path: Path | None = None) -> Recipe:
    """Parse recipe markdown from an in-memory string.

    The structural authority for both files and DB-stored content: `parse_recipe`
    reads a file and delegates here, and the app's storage layer parses the
    markdown it persists the same way. `source_path` is carried onto the Recipe
    for file-origin recipes and left None for DB-origin ones.
    """
    meta, body = _parse_frontmatter(text)

    # Find the H1 title and split on H2 sections
    title_re = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
    h2_re = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

    title_m = title_re.search(body)
    fallback_title = meta.get("title") or (source_path.stem if source_path else "untitled")
    title = title_m.group(1).strip() if title_m else fallback_title
    after_title_start = title_m.end() if title_m else 0
    after_title = body[after_title_start:]

    # Split into (pre-first-H2 intro, sections...)
    sec_matches = list(h2_re.finditer(after_title))
    if not sec_matches:
        intro_text = after_title.strip()
        sections: list[Section] = []
    else:
        intro_text = after_title[: sec_matches[0].start()].strip()
        sections = []
        for i, m in enumerate(sec_matches):
            start = m.end()
            end = sec_matches[i + 1].start() if i + 1 < len(sec_matches) else len(after_title)
            sec_body = after_title[start:end].splitlines()
            sec_intro, blocks, prose = _parse_section_body(sec_body)
            sections.append(
                Section(
                    name=m.group(1).strip(),
                    intro=sec_intro,
                    blocks=blocks,
                    prose=prose,
                )
            )

    return Recipe(
        meta=meta,
        title=title,
        intro=intro_text,
        sections=sections,
        source_path=source_path,
    )


def parse_recipe(path: Path) -> Recipe:
    """Parse a recipe markdown file from disk."""
    return parse_recipe_text(path.read_text(encoding="utf-8"), source_path=path)


def find_recipes(root: Path) -> list[Path]:
    """Walk the recipe tree and return all recipe .md files.

    Skips any path component starting with ``_`` (build machinery: _tools/,
    _templates/, _app/) or ``.`` (dotdirs: .venv/, .git/, .github/) — no recipe
    lives there — and the generated README.md.
    """
    out: list[Path] = []
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(("_", ".")) for part in p.relative_to(root).parts):
            continue
        if p.name == "README.md":
            continue
        out.append(p)
    return out


if __name__ == "__main__":
    # smoke test
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    for rp in find_recipes(root):
        r = parse_recipe(rp)
        print(f"{rp.relative_to(root)}: {r.title} ({len(r.sections)} sections)")
        for s in r.sections:
            subs = ", ".join(s.blocks.keys()) or ("prose" if s.prose else "empty")
            print(f"  ## {s.name} [{subs}]")
