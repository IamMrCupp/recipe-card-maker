"""Geometry tests for the 4x6 recipe card.

`test_pdf_smoke` proves the card builds and builds the same way twice; these
assert on where things actually land. Both defects covered here were reported
from printed output: a long title clipped at both card edges, and a trailing
method step stranded alone on a third card.

The fixture recipe is the one that showed both — a 48-character title and a
method that lands a hair over two landscape cards.
"""

from __future__ import annotations

from pathlib import Path

import make_cards_pdf as cards
import pytest
from recipe_parser import parse_recipe
from reportlab.pdfbase.pdfmetrics import stringWidth

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "_fixtures" / "sweet_potato_sheet_cake.md"
RECIPES = [
    REPO_ROOT / "cookies" / "sun_and_moon.md",
    REPO_ROOT / "cakes" / "erdbeertorte.md",
    FIXTURE,
]

PORTRAIT = cards.CARD_SIZE
LANDSCAPE = (cards.CARD_SIZE[1], cards.CARD_SIZE[0])
ORIENTATIONS = [("portrait", PORTRAIT), ("landscape", LANDSCAPE)]


def usable_width(page_size: tuple[float, float]) -> float:
    return page_size[0] - cards.PADS["left"] - cards.PADS["right"]


@pytest.fixture(params=RECIPES, ids=lambda p: p.stem)
def recipe(request):
    return parse_recipe(request.param)


@pytest.fixture(params=ORIENTATIONS, ids=lambda o: o[0])
def page_size(request):
    return request.param[1]


# --- the title must never run off the card ----------------------------------


@pytest.mark.parametrize("continued", [False, True], ids=["first", "continued"])
def test_no_header_line_overflows_the_card(recipe, page_size, continued):
    width = usable_width(page_size)
    for line in cards.header_lines(recipe, width, continued=continued):
        drawn = stringWidth(line.text, line.font, line.size)
        assert drawn <= width, f"{line.text!r} is {drawn:.1f}pt wide on a {width:.1f}pt card"


def test_long_title_wraps_instead_of_being_clipped():
    """The reported defect: 'Sweet Potato Sheet Cake with Marshmallow Frosting'
    rendered as 'Potato Sheet Cake with Marshmallow F' on the portrait card."""
    recipe = parse_recipe(FIXTURE)
    lines = cards.header_lines(recipe, usable_width(PORTRAIT), continued=False)
    title_lines = [ln.text for ln in lines if ln.font == "Times-Bold"]

    assert len(title_lines) == 2, "the title should wrap, not shrink to illegibility"
    assert " ".join(title_lines) == recipe.title, "no word may be dropped in the wrap"
    assert lines[0].size == cards.TITLE_SIZE, "wrapping should come before shrinking"


def test_unbreakable_title_shrinks_below_the_floor_rather_than_overflowing():
    """A single word wider than the card can't wrap, so it has to shrink."""
    word = "Pfannkuchen" * 6
    size, lines = cards._fit_title(
        word,
        usable_width(PORTRAIT),
        size=cards.TITLE_SIZE,
        min_size=cards.TITLE_MIN_SIZE,
        max_lines=cards.MAX_TITLE_LINES,
    )
    assert lines == [word]
    assert size < cards.TITLE_MIN_SIZE
    assert stringWidth(word, "Times-Bold", size) <= usable_width(PORTRAIT)


def test_running_head_stays_on_one_line(recipe, page_size):
    """A second line of running head costs its height on every continuation card."""
    lines = cards.header_lines(recipe, usable_width(page_size), continued=True)
    assert len(lines) == cards.MAX_CONT_TITLE_LINES
    assert lines[0].text.endswith("— continued")


# --- the body frame has to start below the header, not under it --------------


def test_body_frame_starts_below_the_header_rule(recipe, page_size):
    """The frame height is derived from the measured header; this is the check
    that the two agree, so header text can never print over the first section."""
    first, cont = cards._make_page_templates(recipe, page_size)

    for template, continued in ((first, False), (cont, True)):
        lines = cards.header_lines(recipe, usable_width(page_size), continued=continued)
        text_bottom = page_size[1] - cards.PADS["top"] - sum(ln.leading for ln in lines)
        rule_y = text_bottom - cards.RULE_GAP

        frame = template.frames[0]
        frame_top = frame._y1 + frame.height
        assert frame_top <= rule_y, "body frame overlaps the header rule"
        assert rule_y - frame_top == pytest.approx(cards.FRAME_GAP)
        assert frame._y1 == pytest.approx(cards.PADS["bottom"])


def test_header_height_tracks_its_content(recipe, page_size):
    lines = cards.header_lines(recipe, usable_width(page_size), continued=False)
    expected = sum(ln.leading for ln in lines) + cards.RULE_GAP + cards.FRAME_GAP
    assert cards.header_height(lines) == pytest.approx(expected)


def test_two_line_meta_does_not_collide_with_the_rule():
    """Both seed recipes wrap their yield/timing line; it used to land on the rule."""
    recipe = parse_recipe(REPO_ROOT / "cookies" / "sun_and_moon.md")
    lines = cards.header_lines(recipe, usable_width(PORTRAIT), continued=False)
    meta_lines = [ln for ln in lines if ln.size == cards.META_SIZE]

    assert len(meta_lines) > 1, "fixture no longer exercises a wrapped meta line"
    assert cards.header_height(lines) == pytest.approx(
        sum(ln.leading for ln in lines) + cards.RULE_GAP + cards.FRAME_GAP
    )


# --- no card should end on a near-empty page ---------------------------------


def test_no_card_ends_on_a_widow_page(recipe, page_size, tmp_path):
    landscape = page_size == LANDSCAPE
    out = tmp_path / "card.pdf"
    render = cards.build_pdf(recipe, out, landscape=landscape)
    assert not render.has_widow, (
        f"last card is only {render.last_page_fill:.0%} full across {render.pages} cards"
    )


def test_trailing_step_no_longer_spills_onto_its_own_card():
    """The reported defect: the landscape card ran to three pages, the third
    holding nothing but method step 15."""
    recipe = parse_recipe(FIXTURE)
    unsqueezed = cards._render_card(recipe, LANDSCAPE, 1.0)
    assert unsqueezed.pages == 3, "fixture no longer reproduces the widow"
    assert unsqueezed.has_widow

    chosen = cards._render_card(recipe, LANDSCAPE, 0.97)
    assert chosen.pages == 2
    assert not chosen.has_widow


def test_cards_without_a_widow_are_left_untouched(recipe, page_size, tmp_path):
    """The squeeze is a last resort — a card that already flows well keeps its
    full leading, so fixing one recipe can't quietly reflow the whole corpus."""
    landscape = page_size == LANDSCAPE
    if cards._render_card(recipe, page_size, 1.0).has_widow:
        pytest.skip("this recipe needs the squeeze")
    assert cards.build_pdf(recipe, tmp_path / "card.pdf", landscape=landscape).squeeze == 1.0


def test_squeeze_keeps_font_sizes_and_only_tightens_leading():
    tight = cards._squeezed_styles(0.9)
    for name, base in cards.STYLES.items():
        assert tight[name].fontSize == base.fontSize, f"{name} font size changed"
        assert tight[name].leading == pytest.approx(base.leading * 0.9)
        assert tight[name].leading > tight[name].fontSize, f"{name} lines would touch"


def test_fixture_card_is_deterministic(tmp_path):
    """The squeeze search must not make the output depend on build order."""
    recipe = parse_recipe(FIXTURE)
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    cards.build_pdf(recipe, a, landscape=True)
    cards.build_pdf(recipe, b, landscape=True)
    assert a.read_bytes() == b.read_bytes()
