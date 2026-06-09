"""Generate 4x6 recipe-card PDFs from recipe markdown files.

Each PDF is a multi-page 4" x 6" document. ReportLab handles pagination —
sections flow naturally; the first page gets the full title header and the
subsequent "continued" pages get a shorter header.

Usage:
    python _tools/make_cards_pdf.py             # regenerate all
    python _tools/make_cards_pdf.py cookies/sun_and_moon.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _buildmeta import ensure_reproducible_pdf_dates  # noqa: E402
from _styles import ACCENT, INK, RULE, SOFT, md_inline  # noqa: E402
from recipe_parser import Recipe, Section, find_recipes, parse_recipe  # noqa: E402

CARD_SIZE = (4 * inch, 6 * inch)

_base = getSampleStyleSheet()

STYLES = {
    "title": ParagraphStyle(
        "T",
        parent=_base["Title"],
        fontName="Times-Bold",
        fontSize=17,
        leading=19,
        textColor=ACCENT,
        alignment=TA_CENTER,
        spaceAfter=2,
    ),
    "subtitle": ParagraphStyle(
        "ST",
        parent=_base["Normal"],
        fontName="Times-Italic",
        fontSize=9,
        leading=11,
        textColor=SOFT,
        alignment=TA_CENTER,
        spaceAfter=4,
    ),
    "meta": ParagraphStyle(
        "M",
        parent=_base["Normal"],
        fontName="Times-Italic",
        fontSize=8.5,
        leading=11,
        textColor=SOFT,
        alignment=TA_CENTER,
        spaceAfter=4,
    ),
    # Content styles are sized for density — a recipe-tin card should fit on as few
    # cards as possible while staying readable for kitchen reference (~8pt body).
    # `keepWithNext` on the headers stops a section/sub title stranding alone at a
    # page bottom (it moves to the next card with its content).
    "section": ParagraphStyle(
        "SEC",
        parent=_base["Normal"],
        fontName="Times-Bold",
        fontSize=9,
        leading=10.5,
        textColor=ACCENT,
        spaceBefore=3,
        spaceAfter=2,
        keepWithNext=1,
    ),
    "sub": ParagraphStyle(
        "SUB",
        parent=_base["Normal"],
        fontName="Times-Bold",
        fontSize=7.5,
        leading=8.5,
        textColor=INK,
        spaceBefore=2,
        spaceAfter=1,
        keepWithNext=1,
    ),
    "body": ParagraphStyle(
        "B",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=7,
        leading=8.5,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=2,
    ),
    "bullet": ParagraphStyle(
        "BU",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=7,
        leading=8.5,
        textColor=INK,
        leftIndent=10,
        firstLineIndent=-8,
        spaceAfter=1,
    ),
    "step": ParagraphStyle(
        "ST2",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=7,
        leading=8.5,
        textColor=INK,
        alignment=TA_JUSTIFY,
        leftIndent=14,
        firstLineIndent=-14,
        spaceAfter=2,
    ),
    "note": ParagraphStyle(
        "N",
        parent=_base["Normal"],
        fontName="Times-Italic",
        fontSize=7,
        leading=8.5,
        textColor=SOFT,
        alignment=TA_JUSTIFY,
        spaceAfter=2,
    ),
}


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=2, spaceAfter=3)


_ENTITY_RE = re.compile(r"&nbsp;|&amp;|&lt;|&gt;|&#\d+;|&[a-zA-Z]+;")


def _strip_entities(s: str) -> str:
    """Replace HTML entities with plain equivalents for canvas-drawn text."""
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    s = s.replace("&lt;", "<").replace("&gt;", ">")
    # Collapse any runs of whitespace
    return re.sub(r"\s+", " ", s).strip()


def _meta_line(recipe: Recipe) -> str | None:
    """Build a terse 'yield | timing | bake' line from frontmatter + section 1."""
    meta = recipe.meta
    bits: list[str] = []
    if meta.get("yield"):
        bits.append(str(meta["yield"]))
    # Prefer explicit timing from the 'Yield and timing' section if present
    yt = recipe.section("Yield and timing")
    if yt and yt.prose:
        timing_lines = [
            p.lstrip("-*• ").strip() for p in yt.prose if p.lstrip().startswith(("-", "*"))
        ]
        timing = next((t for t in timing_lines if "Active" in t), None)
        if timing:
            bits.append(timing)
    if not bits:
        return None
    return _strip_entities("  |  ".join(bits))


def _render_section_flow(section: Section) -> list:
    """Render a section as a stream of flowables for the card layout."""
    # Skip 'Yield and timing' here — it goes into the meta header on card 1
    if section.name.lower().startswith("yield"):
        return []

    out = [Paragraph(section.name.upper(), STYLES["section"])]

    if section.intro:
        for para in _split_paragraphs(section.intro):
            out.append(Paragraph(md_inline(para), STYLES["body"]))

    if section.blocks:
        for sub_name, items in section.blocks.items():
            out.append(Paragraph(f"<b>{sub_name}</b>", STYLES["sub"]))
            if sub_name.lower() in ("method", "assembly", "instructions", "steps"):
                for i, item in enumerate(items, 1):
                    out.append(
                        Paragraph(
                            f"<b>{i}.</b>&nbsp; {md_inline(item)}",
                            STYLES["step"],
                        )
                    )
            else:
                for item in items:
                    out.append(Paragraph(f"•&nbsp;&nbsp;{md_inline(item)}", STYLES["bullet"]))
    elif section.prose:
        for block in section.prose:
            if block.startswith(("- ", "* ")):
                out.append(Paragraph(f"•&nbsp;&nbsp;{md_inline(block[2:])}", STYLES["bullet"]))
            elif re.match(r"^\d+\.\s", block):
                n, _, rest = block.partition(". ")
                out.append(Paragraph(f"<b>{n}.</b>&nbsp; {md_inline(rest)}", STYLES["step"]))
            else:
                out.append(Paragraph(md_inline(block), STYLES["body"]))

    return out


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


# --- Page templates with headers ---------------------------------------------


def _make_page_templates(recipe: Recipe, page_size: tuple[float, float] = CARD_SIZE):
    """Two templates: 'first' has the full title header, 'cont' has a small one.

    `page_size` is the card dimensions — (4×6) portrait by default, (6×4) for the
    landscape variant. All frame/header geometry derives from it, so the same code
    lays out either orientation."""
    pad_left = 0.2 * inch
    pad_right = 0.2 * inch
    pad_top = 0.18 * inch
    pad_bottom = 0.18 * inch

    # First page: bigger header leaves less room for body
    first_header_h = 1.0 * inch
    first_frame = Frame(
        pad_left,
        pad_bottom,
        page_size[0] - pad_left - pad_right,
        page_size[1] - pad_top - pad_bottom - first_header_h,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="first_body",
        showBoundary=0,
    )

    cont_header_h = 0.4 * inch
    cont_frame = Frame(
        pad_left,
        pad_bottom,
        page_size[0] - pad_left - pad_right,
        page_size[1] - pad_top - pad_bottom - cont_header_h,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="cont_body",
        showBoundary=0,
    )

    subtitle = _subtitle_from_meta(recipe.meta)
    meta_line = _meta_line(recipe)

    def draw_first_header(canvas, doc):
        canvas.saveState()
        w, h = page_size
        # Title
        canvas.setFont("Times-Bold", 17)
        canvas.setFillColor(ACCENT)
        canvas.drawCentredString(w / 2, h - pad_top - 15, recipe.title)
        y = h - pad_top - 15 - 14
        if subtitle:
            canvas.setFont("Times-Italic", 9)
            canvas.setFillColor(SOFT)
            _draw_centered_wrapped(
                canvas, subtitle, w / 2, y, max_width=w - pad_left - pad_right - 10, line_height=11
            )
            y -= 22
        if meta_line:
            canvas.setFont("Times-Italic", 8.5)
            canvas.setFillColor(SOFT)
            _draw_centered_wrapped(
                canvas, meta_line, w / 2, y, max_width=w - pad_left - pad_right - 10, line_height=11
            )
            y -= 14
        # Rule
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(pad_left, y, w - pad_right, y)
        canvas.restoreState()

    def draw_cont_header(canvas, doc):
        canvas.saveState()
        w, h = page_size
        canvas.setFont("Times-Bold", 13)
        canvas.setFillColor(ACCENT)
        canvas.drawCentredString(w / 2, h - pad_top - 11, f"{recipe.title} — continued")
        y = h - pad_top - 11 - 8
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(pad_left, y, w - pad_right, y)
        canvas.restoreState()

    return [
        PageTemplate(
            id="first", frames=[first_frame], onPage=draw_first_header, pagesize=page_size
        ),
        PageTemplate(id="cont", frames=[cont_frame], onPage=draw_cont_header, pagesize=page_size),
    ]


def _draw_centered_wrapped(canvas, text, cx, y, max_width, line_height):
    """Primitive centered word-wrap for canvas-drawn header text."""
    words = text.split()
    lines = []
    line: list[str] = []
    for w in words:
        test = " ".join(line + [w])
        if canvas.stringWidth(test) <= max_width:
            line.append(w)
        else:
            if line:
                lines.append(" ".join(line))
            line = [w]
    if line:
        lines.append(" ".join(line))
    for i, ln in enumerate(lines):
        canvas.drawCentredString(cx, y - i * line_height, ln)


def _subtitle_from_meta(meta: dict) -> str | None:
    bits = []
    cuisine = meta.get("cuisine")
    source = meta.get("source")
    if cuisine:
        bits.append(cuisine.replace("_", " ").title())
    if source:
        bits.append(f"via {source}")
    return " · ".join(bits) if bits else None


# --- Build ------------------------------------------------------------------


def build_pdf(recipe: Recipe, out_path: Path, *, landscape: bool = False) -> None:
    """Render the recipe-tin card. Default is 4×6 portrait (the committed
    `_4x6.pdf`); `landscape=True` produces a 6×4 card (long edge horizontal)."""
    ensure_reproducible_pdf_dates()
    page_size = (CARD_SIZE[1], CARD_SIZE[0]) if landscape else CARD_SIZE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(out_path),
        pagesize=page_size,
        leftMargin=0.2 * inch,
        rightMargin=0.2 * inch,
        topMargin=0.18 * inch,
        bottomMargin=0.18 * inch,
        title=recipe.title,
        author=recipe.meta.get("source", "Aaron's kitchen"),
    )
    doc.addPageTemplates(_make_page_templates(recipe, page_size))

    story: list = [NextPageTemplate("cont")]
    for section in recipe.sections:
        story.extend(_render_section_flow(section))

    note = recipe.meta.get("notes")
    if note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<i>{md_inline(note)}</i>", STYLES["note"]))

    doc.build(story)


def main():
    root = Path(__file__).resolve().parent.parent
    args = sys.argv[1:]
    if args:
        targets = [root / a for a in args]
    else:
        targets = find_recipes(root)

    for src in targets:
        recipe = parse_recipe(src)
        out = src.with_name(f"{src.stem}_4x6.pdf")
        build_pdf(recipe, out)
        print(f"  wrote {out.relative_to(root)}")


if __name__ == "__main__":
    main()
