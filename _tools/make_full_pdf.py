"""Generate full letter-size PDFs from recipe markdown files.

Usage:
    python _tools/make_full_pdf.py             # regenerate all
    python _tools/make_full_pdf.py cookies/sun_and_moon.md   # regenerate one
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _buildmeta import ensure_reproducible_pdf_dates  # noqa: E402
from _styles import ACCENT, INK, RULE, SOFT, md_inline  # noqa: E402
from recipe_parser import Recipe, Section, find_recipes, parse_recipe  # noqa: E402

# --- Style kit -------------------------------------------------------------

_base = getSampleStyleSheet()

STYLES = {
    "title": ParagraphStyle(
        "T",
        parent=_base["Title"],
        fontName="Times-Bold",
        fontSize=26,
        leading=30,
        textColor=ACCENT,
        alignment=TA_CENTER,
        spaceAfter=4,
    ),
    "subtitle": ParagraphStyle(
        "ST",
        parent=_base["Normal"],
        fontName="Times-Italic",
        fontSize=12,
        leading=15,
        textColor=SOFT,
        alignment=TA_CENTER,
        spaceAfter=14,
    ),
    "intro": ParagraphStyle(
        "I",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
    ),
    "h2": ParagraphStyle(
        "H2",
        parent=_base["Heading2"],
        fontName="Times-Bold",
        fontSize=14,
        leading=17,
        textColor=ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    ),
    "h3": ParagraphStyle(
        "H3",
        parent=_base["Heading3"],
        fontName="Times-Bold",
        fontSize=11.5,
        leading=14,
        textColor=INK,
        spaceBefore=8,
        spaceAfter=3,
    ),
    "body": ParagraphStyle(
        "B",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=7,
    ),
    "bullet": ParagraphStyle(
        "BU",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        textColor=INK,
        leftIndent=16,
        bulletIndent=4,
        spaceAfter=2,
    ),
    "step": ParagraphStyle(
        "ST2",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        textColor=INK,
        alignment=TA_JUSTIFY,
        leftIndent=20,
        bulletIndent=4,
        spaceAfter=6,
    ),
    "note": ParagraphStyle(
        "N",
        parent=_base["Normal"],
        fontName="Times-Italic",
        fontSize=10,
        leading=13,
        textColor=SOFT,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ),
}


def _rule():
    return [
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=0.6, color=RULE),
        Spacer(1, 8),
    ]


# --- Story builders -------------------------------------------------------


def _subtitle_from_meta(meta: dict) -> str | None:
    bits = []
    cuisine = meta.get("cuisine")
    source = meta.get("source")
    if cuisine:
        bits.append(cuisine.replace("_", " ").title())
    if source:
        bits.append(f"via {source}")
    return " &middot; ".join(bits) if bits else None


def _render_section(section: Section) -> list:
    out = [Paragraph(section.name, STYLES["h2"])]

    if section.intro:
        for para in _split_paragraphs(section.intro):
            out.append(Paragraph(md_inline(para), STYLES["body"]))

    if section.blocks:
        for sub_name, items in section.blocks.items():
            out.append(Paragraph(f"<b>{sub_name}</b>", STYLES["h3"]))
            if sub_name.lower() in ("method", "assembly", "instructions", "steps"):
                for i, item in enumerate(items, 1):
                    out.append(
                        Paragraph(
                            f"<b>{i}.</b> &nbsp; {md_inline(item)}",
                            STYLES["step"],
                        )
                    )
            else:
                # bullets (ingredients, notes, variations, etc.)
                for item in items:
                    out.append(Paragraph(f"• {md_inline(item)}", STYLES["bullet"]))
    elif section.prose:
        for block in section.prose:
            if block.startswith("- ") or block.startswith("* "):
                out.append(Paragraph(f"• {md_inline(block[2:])}", STYLES["bullet"]))
            elif re.match(r"^\d+\.\s", block):
                n, _, rest = block.partition(". ")
                out.append(
                    Paragraph(
                        f"<b>{n}.</b> &nbsp; {md_inline(rest)}",
                        STYLES["step"],
                    )
                )
            else:
                out.append(Paragraph(md_inline(block), STYLES["body"]))

    return out


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def build_story(recipe: Recipe) -> list:
    story: list = []
    story.append(Paragraph(recipe.title, STYLES["title"]))
    subtitle = _subtitle_from_meta(recipe.meta)
    if subtitle:
        story.append(Paragraph(subtitle, STYLES["subtitle"]))
    story.extend(_rule())

    if recipe.intro:
        for para in _split_paragraphs(recipe.intro):
            story.append(Paragraph(md_inline(para), STYLES["intro"]))

    for section in recipe.sections:
        story.extend(_render_section(section))

    # Footer note from frontmatter
    note = recipe.meta.get("notes")
    if note:
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"<i>{md_inline(note)}</i>", STYLES["note"]))

    return story


def build_pdf(recipe: Recipe, out_path: Path) -> None:
    ensure_reproducible_pdf_dates()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=recipe.title,
        author=recipe.meta.get("source", "Aaron's kitchen"),
    )
    doc.build(build_story(recipe))


def main():
    root = Path(__file__).resolve().parent.parent
    args = sys.argv[1:]
    if args:
        targets = [root / a for a in args]
    else:
        targets = find_recipes(root)

    for src in targets:
        recipe = parse_recipe(src)
        out = src.with_name(f"{src.stem}_full.pdf")
        build_pdf(recipe, out)
        print(f"  wrote {out.relative_to(root)}")


if __name__ == "__main__":
    main()
