"""Generate 4x6 recipe-card PDFs from recipe markdown files.

Each PDF is a multi-page 4" x 6" document. ReportLab handles pagination —
sections flow naturally; the first page gets the full title header and the
subsequent "continued" pages get a shorter header.

Usage:
    python _tools/make_cards_pdf.py             # regenerate all
    python _tools/make_cards_pdf.py cookies/sun_and_moon.md
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import NamedTuple

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
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
    # Content styles are sized for density — a recipe-tin card should fit on as few
    # cards as possible while staying readable for kitchen reference (~6pt body).
    # `keepWithNext` on the headers stops a section/sub title stranding alone at a
    # page bottom (it moves to the next card with its content).
    "section": ParagraphStyle(
        "SEC",
        parent=_base["Normal"],
        fontName="Times-Bold",
        fontSize=8,
        leading=9,
        textColor=ACCENT,
        spaceBefore=2,
        spaceAfter=1,
        keepWithNext=1,
    ),
    "sub": ParagraphStyle(
        "SUB",
        parent=_base["Normal"],
        fontName="Times-Bold",
        fontSize=6.5,
        leading=7.5,
        textColor=INK,
        spaceBefore=2,
        spaceAfter=1,
        keepWithNext=1,
    ),
    "body": ParagraphStyle(
        "B",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=6,
        leading=7.5,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=2,
    ),
    "bullet": ParagraphStyle(
        "BU",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=6,
        leading=7.5,
        textColor=INK,
        leftIndent=10,
        firstLineIndent=-8,
        spaceAfter=1,
    ),
    "step": ParagraphStyle(
        "ST2",
        parent=_base["Normal"],
        fontName="Times-Roman",
        fontSize=6,
        leading=7.5,
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
        fontSize=6,
        leading=7.5,
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


def _scaled_styles(font_scale: float, leading_squeeze: float = 1.0) -> dict[str, ParagraphStyle]:
    """`STYLES` with the type scaled by `font_scale`, leading tightened on top of
    that by `leading_squeeze`.

    The two are separate knobs because they buy different things. Shrinking the
    type is how a long recipe reaches a single card — visible, so it is bounded by
    `MIN_BODY_SIZE`. Tightening leading alone leaves the card exactly as readable
    as it was and is the invisible nudge that clears a widow page. See `_fit_card`.
    """
    if font_scale == 1.0 and leading_squeeze == 1.0:
        return STYLES
    out = {}
    for name, base in STYLES.items():
        style = ParagraphStyle(f"{base.name}-s", parent=base)
        style.fontSize = base.fontSize * font_scale
        style.leading = base.leading * font_scale * leading_squeeze
        style.spaceBefore = base.spaceBefore * font_scale * leading_squeeze
        style.spaceAfter = base.spaceAfter * font_scale * leading_squeeze
        style.leftIndent = base.leftIndent * font_scale
        style.firstLineIndent = base.firstLineIndent * font_scale
        out[name] = style
    return out


def _render_section_flow(section: Section, styles: dict[str, ParagraphStyle]) -> list:
    """Render a section as a stream of flowables for the card layout."""
    # Skip 'Yield and timing' here — it goes into the meta header on card 1
    if section.name.lower().startswith("yield"):
        return []

    out = [Paragraph(section.name.upper(), styles["section"])]

    if section.intro:
        for para in _split_paragraphs(section.intro):
            out.append(Paragraph(md_inline(para), styles["body"]))

    if section.blocks:
        for sub_name, items in section.blocks.items():
            out.append(Paragraph(f"<b>{sub_name}</b>", styles["sub"]))
            if sub_name.lower() in ("method", "assembly", "instructions", "steps"):
                for i, item in enumerate(items, 1):
                    out.append(
                        Paragraph(
                            f"<b>{i}.</b>&nbsp; {md_inline(item)}",
                            styles["step"],
                        )
                    )
            else:
                for item in items:
                    out.append(Paragraph(f"•&nbsp;&nbsp;{md_inline(item)}", styles["bullet"]))
    elif section.prose:
        for block in section.prose:
            if block.startswith(("- ", "* ")):
                out.append(Paragraph(f"•&nbsp;&nbsp;{md_inline(block[2:])}", styles["bullet"]))
            elif re.match(r"^\d+\.\s", block):
                n, _, rest = block.partition(". ")
                out.append(Paragraph(f"<b>{n}.</b>&nbsp; {md_inline(rest)}", styles["step"]))
            else:
                out.append(Paragraph(md_inline(block), styles["body"]))

    return out


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


# --- Header layout -----------------------------------------------------------
#
# The header is drawn straight onto the canvas, so the body Frame has to be told
# how much room it took. That height is measured from the real wrapped lines
# rather than assumed: reserving a fixed slab both clipped long titles (they were
# centred on a box wider than the card) and wasted height on short ones — costly
# on the 6x4 card, where every reclaimed point is another line of method.

PADS = {"left": 0.2 * inch, "right": 0.2 * inch, "top": 0.18 * inch, "bottom": 0.18 * inch}

TITLE_SIZE = 17  # shrunk toward TITLE_MIN_SIZE until the title fits MAX_TITLE_LINES
TITLE_MIN_SIZE = 10
CONT_TITLE_SIZE = 13
CONT_TITLE_MIN_SIZE = 9
MAX_TITLE_LINES = 2
# The running head is kept to one line where it can be: a second line costs its
# height on *every* continuation card, so a long title shrinks instead of wrapping.
MAX_CONT_TITLE_LINES = 1
SUBTITLE_SIZE = 9
META_SIZE = 8.5
LINE_SPACING = 1.2  # leading as a multiple of font size
BLOCK_GAP = 3.0  # title -> subtitle/meta, so they read as separate blocks
COLUMN_GUTTER = 10.0  # between body columns, where there is more than one
RULE_GAP = 4.0  # last header line -> rule
FRAME_GAP = 4.0  # rule -> top of the body frame


class HeaderLine(NamedTuple):
    """One laid-out line of canvas-drawn header text."""

    text: str
    font: str
    size: float
    color: object
    gap_before: float = 0.0

    @property
    def leading(self) -> float:
        return self.size * LINE_SPACING + self.gap_before


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word wrap. A word wider than `max_width` still gets its own line."""
    lines: list[str] = []
    line: list[str] = []
    for word in text.split():
        if line and stringWidth(" ".join(line + [word]), font, size) > max_width:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return lines or [""]


def _fit_title(
    text: str, max_width: float, *, size: float, min_size: float, max_lines: int
) -> tuple[float, list[str]]:
    """Largest size <= `size` at which `text` wraps into `max_lines` fitting lines.

    Shrinks in half-point steps to `min_size`, then allows more lines at that floor,
    and only shrinks past it when a single unbreakable word is still wider than the
    card. The guarantee the caller depends on: no returned line overflows `max_width`.
    """

    def fits(trial: float) -> list[str] | None:
        lines = _wrap(text, "Times-Bold", trial, max_width)
        if all(stringWidth(ln, "Times-Bold", trial) <= max_width for ln in lines):
            return lines
        return None

    trial = size
    while trial >= min_size:
        lines = fits(trial)
        if lines is not None and len(lines) <= max_lines:
            return trial, lines
        trial -= 0.5

    trial = min_size
    while trial > 1:
        lines = fits(trial)
        if lines is not None:
            return trial, lines
        trial -= 0.5
    return trial, _wrap(text, "Times-Bold", trial, max_width)


def header_lines(recipe: Recipe, usable_width: float, *, continued: bool) -> list[HeaderLine]:
    """The exact lines the page header will draw, in order."""
    title = _strip_entities(recipe.title)
    if continued:
        size, lines = _fit_title(
            f"{title} \u2014 continued",
            usable_width,
            size=CONT_TITLE_SIZE,
            min_size=CONT_TITLE_MIN_SIZE,
            max_lines=MAX_CONT_TITLE_LINES,
        )
        return [HeaderLine(ln, "Times-Bold", size, ACCENT) for ln in lines]

    size, lines = _fit_title(
        title,
        usable_width,
        size=TITLE_SIZE,
        min_size=TITLE_MIN_SIZE,
        max_lines=MAX_TITLE_LINES,
    )
    out = [HeaderLine(ln, "Times-Bold", size, ACCENT) for ln in lines]

    subtitle = _subtitle_from_meta(recipe.meta)
    if subtitle:
        out += [
            HeaderLine(ln, "Times-Italic", SUBTITLE_SIZE, SOFT, BLOCK_GAP if i == 0 else 0.0)
            for i, ln in enumerate(
                _wrap(_strip_entities(subtitle), "Times-Italic", SUBTITLE_SIZE, usable_width)
            )
        ]

    meta_line = _meta_line(recipe)
    if meta_line:
        gap = BLOCK_GAP if not subtitle else 0.0
        out += [
            HeaderLine(ln, "Times-Italic", META_SIZE, SOFT, gap if i == 0 else 0.0)
            for i, ln in enumerate(_wrap(meta_line, "Times-Italic", META_SIZE, usable_width))
        ]
    return out


def header_height(lines: list[HeaderLine]) -> float:
    """Height the header occupies, rule and breathing room included."""
    return sum(ln.leading for ln in lines) + RULE_GAP + FRAME_GAP


def _draw_header(canvas, lines: list[HeaderLine], page_size: tuple[float, float]) -> None:
    w, h = page_size
    canvas.saveState()
    y = h - PADS["top"]
    for ln in lines:
        y -= ln.leading
        canvas.setFont(ln.font, ln.size)
        canvas.setFillColor(ln.color)
        # The gap sits above the line; the baseline then sits `size` below the
        # line box top, which leaves the descender its room before the next line.
        canvas.drawCentredString(w / 2, y + ln.leading - ln.gap_before - ln.size, ln.text)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(PADS["left"], y - RULE_GAP, w - PADS["right"], y - RULE_GAP)
    canvas.restoreState()


# --- Page templates ----------------------------------------------------------


def _make_page_templates(
    recipe: Recipe, page_size: tuple[float, float] = CARD_SIZE, columns: int = 1
):
    """Two templates: 'first' has the full title header, 'cont' has a small one.

    `page_size` is the card dimensions — (4x6) portrait by default, (6x4) for the
    landscape variant. All frame/header geometry derives from it, so the same code
    lays out either orientation.

    `columns` splits the body into side-by-side frames that content flows through
    in order. The 6x4 card uses two: a single 403pt column runs to ~130 characters
    a line, and a list of short ingredients wastes most of every line it sits on.
    """
    usable_width = page_size[0] - PADS["left"] - PADS["right"]
    column_width = (usable_width - COLUMN_GUTTER * (columns - 1)) / columns

    def body_frames(lines: list[HeaderLine], tag: str) -> list[Frame]:
        height = page_size[1] - PADS["top"] - PADS["bottom"] - header_height(lines)
        return [
            Frame(
                PADS["left"] + i * (column_width + COLUMN_GUTTER),
                PADS["bottom"],
                column_width,
                height,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
                id=f"{tag}{i}",
                showBoundary=0,
            )
            for i in range(columns)
        ]

    first_lines = header_lines(recipe, usable_width, continued=False)
    cont_lines = header_lines(recipe, usable_width, continued=True)

    def draw_first_header(canvas, doc):
        _draw_header(canvas, first_lines, page_size)

    def draw_cont_header(canvas, doc):
        _draw_header(canvas, cont_lines, page_size)

    return [
        PageTemplate(
            id="first",
            frames=body_frames(first_lines, "first_body"),
            onPage=draw_first_header,
            pagesize=page_size,
        ),
        PageTemplate(
            id="cont",
            frames=body_frames(cont_lines, "cont_body"),
            onPage=draw_cont_header,
            pagesize=page_size,
        ),
    ]


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
#
# A 6x4 card is meant to be pulled out of the tin and cooked from, so the layout
# is chosen in this order:
#   1. one card at full size,
#   2. one card with the type shrunk, but never below MIN_BODY_SIZE,
#   3. full size, with leading tightened just enough that the last card isn't a
#      near-empty widow.
# Step 2 is bounded on purpose. Every recipe in the corpus *could* be squeezed
# onto a single card by going small enough; most of them only at sizes nobody
# wants to cook from. Where the floor is reached, two cards is the honest answer.

BODY_SIZE = STYLES["body"].fontSize
MIN_BODY_SIZE = 5.0  # the smallest body type worth printing; full size is 6pt
FIT_STEPS = (0.98, 0.96, 0.94, 0.92, 0.90, 0.88, 0.86, 0.84)
SQUEEZE_STEPS = (0.97, 0.94, 0.91)
MIN_LAST_PAGE_FILL = 0.15

# The 6x4 card reads as two columns; the 4x6 is too narrow to split (half of 259pt
# leaves ~40 characters a line, which justified method steps can't carry).
LANDSCAPE_COLUMNS = 2
PORTRAIT_COLUMNS = 1


class CardRender(NamedTuple):
    data: bytes
    pages: int
    last_page_fill: float  # 0..1 — how much of the final card's columns are used
    body_size: float  # the body type size this layout settled on
    squeeze: float  # leading tightening applied on top of that

    @property
    def has_widow(self) -> bool:
        return self.pages > 1 and self.last_page_fill < MIN_LAST_PAGE_FILL


def _render_card(
    recipe: Recipe,
    page_size: tuple[float, float],
    columns: int,
    *,
    font_scale: float = 1.0,
    leading_squeeze: float = 1.0,
) -> CardRender:
    """Lay the card out once at a given size and report how it filled."""
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=PADS["left"],
        rightMargin=PADS["right"],
        topMargin=PADS["top"],
        bottomMargin=PADS["bottom"],
        title=recipe.title,
        author=recipe.meta.get("source", "Aaron's kitchen"),
    )

    fill: dict[int, float] = {}

    def record(canvas, doc_):
        # Every frame of the page, not just the one that happened to be active:
        # on a two-column card, content ending in column 1 leaves column 2 empty,
        # and measuring only the active frame would call a full page a widow.
        frames = doc_.pageTemplate.frames
        used = sum(f._aH - (f._y - f._y1) for f in frames)
        available = sum(f._aH for f in frames)
        fill[doc_.page] = used / available if available else 1.0

    templates = _make_page_templates(recipe, page_size, columns)
    for template in templates:
        template.onPageEnd = record
    doc.addPageTemplates(templates)

    styles = _scaled_styles(font_scale, leading_squeeze)
    story: list = [NextPageTemplate("cont")]
    for section in recipe.sections:
        story.extend(_render_section_flow(section, styles))

    note = recipe.meta.get("notes")
    if note:
        story.append(Spacer(1, 6 * font_scale * leading_squeeze))
        story.append(Paragraph(f"<i>{md_inline(note)}</i>", styles["note"]))

    doc.build(story)
    return CardRender(
        buf.getvalue(),
        doc.page,
        fill.get(doc.page, 1.0),
        BODY_SIZE * font_scale,
        leading_squeeze,
    )


def _fit_card(
    recipe: Recipe,
    page_size: tuple[float, float],
    columns: int,
    *,
    fit_single_card: bool = False,
) -> CardRender:
    """Pick the layout, by the order of preference described above.

    `fit_single_card` enables the shrink-to-one-page step. It is on for the 6x4
    card, which is meant to be cooked from directly, and off for the 4x6, whose
    two pages are the front and back of one card by design — shrinking the type
    there would buy a blank card back.
    """
    full = _render_card(recipe, page_size, columns)
    if full.pages == 1:
        return full

    if fit_single_card:
        for font_scale in FIT_STEPS:
            if BODY_SIZE * font_scale < MIN_BODY_SIZE:
                break
            shrunk = _render_card(recipe, page_size, columns, font_scale=font_scale)
            if shrunk.pages == 1:
                return shrunk

    if not full.has_widow:
        return full  # more than one card, but it breaks cleanly — leave it alone

    best = full  # the untouched layout, kept as the fallback
    for squeeze in SQUEEZE_STEPS:
        render = _render_card(recipe, page_size, columns, leading_squeeze=squeeze)
        if not render.has_widow:
            return render
        if render.pages < best.pages:
            best = render
    return best


def build_pdf(recipe: Recipe, out_path: Path, *, landscape: bool = False) -> CardRender:
    """Render the recipe-tin card. Default is 4x6 portrait (the committed
    `_4x6.pdf`); `landscape=True` produces a 6x4 card (long edge horizontal).

    Returns the layout that was written — page count, how full the last card is,
    the body size it settled on and any leading squeeze. Callers are free to
    ignore it; the tests assert on it rather than re-deriving the geometry from
    the PDF bytes.
    """
    ensure_reproducible_pdf_dates()
    page_size = (CARD_SIZE[1], CARD_SIZE[0]) if landscape else CARD_SIZE
    columns = LANDSCAPE_COLUMNS if landscape else PORTRAIT_COLUMNS
    out_path.parent.mkdir(parents=True, exist_ok=True)

    best = _fit_card(recipe, page_size, columns, fit_single_card=landscape)
    out_path.write_bytes(best.data)
    return best


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
