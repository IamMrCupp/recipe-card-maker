"""Tests for the LLM extraction service (§3.D.1).

No network: a fake Anthropic client returns a recorded `RecipeDraft`, so we test
prompt/content assembly, model selection, markdown rendering, and graceful
degradation — not model accuracy. The renderer is exercised in isolation as the
anchor, and rendered drafts are round-tripped through the real parser to prove
they're valid corpus markdown.
"""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from recipe_parser import parse_recipe_text

from _app.extraction import (
    ClaudeExtractor,
    ExtractionUnavailable,
    ImageInput,
    RecipeDraft,
    get_extractor,
    render_markdown,
)
from _app.llm_config import LLMConfig

CONFIG = LLMConfig(
    api_key="sk-test",
    base_url=None,
    text_model="claude-haiku-4-5",
    vision_model="claude-sonnet-4-6",
)


class FakeMessages:
    def __init__(self, parsed: RecipeDraft | None = None, error: Exception | None = None):
        self._parsed = parsed
        self._error = error
        self.last_kwargs: dict | None = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(parsed_output=self._parsed)


class FakeClient:
    def __init__(self, parsed: RecipeDraft | None = None, error: Exception | None = None):
        self.messages = FakeMessages(parsed=parsed, error=error)


FULL_DRAFT = RecipeDraft(
    title="Lemon Loaf",
    category="cakes",
    cuisine="american",
    tags=["lemon", "quickbread"],
    active_time="20m",
    total_time="1h10m",
    yield_amount="One 9x5 loaf",
    difficulty="easy",
    intro="A bright, simple loaf.",
    ingredients=["200 g flour", "2 lemons, zested"],
    steps=["Mix dry and wet.", "Bake at 175C for 50 minutes."],
)


# --- rendering (the anchor) -------------------------------------------------


def test_render_markdown_shape_and_roundtrip():
    md = render_markdown(FULL_DRAFT)
    assert md.startswith("---\n")
    assert "title: Lemon Loaf" in md
    assert "tags: [lemon, quickbread]" in md
    assert "yield: One 9x5 loaf" in md
    # importer-owned / user-only keys present but blank
    assert "source:" in md and "source_url:" in md
    assert "last_made:" in md and "rating:" in md
    # body sections match the hand-entry STARTER skeleton
    assert "# Lemon Loaf" in md
    assert "## Ingredients" in md and "- 200 g flour" in md
    assert "## Method" in md and "1. Mix dry and wet." in md

    # and it's valid corpus markdown
    recipe = parse_recipe_text(md)
    assert recipe.title == "Lemon Loaf"


def test_render_markdown_empty_draft_is_blank_not_fabricated():
    md = render_markdown(RecipeDraft())
    assert "title:" in md
    assert "tags: []" in md
    # placeholders only — no invented ingredients or steps
    assert "## Ingredients\n\n-\n" in md
    assert "## Method\n\n1.\n" in md
    # still parses (untitled fallback)
    parse_recipe_text(md)


def test_render_markdown_colon_values_unquoted_and_roundtrip():
    # the parser splits on the first colon only, so a colon in the value is safe
    md = render_markdown(RecipeDraft(title="Soup: a study"))
    assert "title: Soup: a study" in md
    assert parse_recipe_text(md).title == "Soup: a study"


def test_render_markdown_quotes_leading_bracket():
    # a leading '[' would read as an inline list — must be quoted
    md = render_markdown(RecipeDraft(yield_amount="[makes 12]"))
    assert 'yield: "[makes 12]"' in md


# --- extraction: text + vision ---------------------------------------------


def test_extract_text_uses_text_model_and_renders():
    client = FakeClient(parsed=FULL_DRAFT)
    md = ClaudeExtractor(CONFIG, client=client).extract(text="some recipe text")
    assert client.messages.last_kwargs["model"] == "claude-haiku-4-5"
    assert "# Lemon Loaf" in md
    # raw text is included as a content block after the instruction
    blocks = client.messages.last_kwargs["messages"][0]["content"]
    assert any(b.get("text") == "some recipe text" for b in blocks)
    assert not any(b["type"] == "image" for b in blocks)


def test_extract_image_uses_vision_model_and_sends_image_block():
    client = FakeClient(parsed=FULL_DRAFT)
    img = ImageInput(data=b"\x89PNGfake", media_type="image/png")
    md = ClaudeExtractor(CONFIG, client=client).extract(image=img)
    assert client.messages.last_kwargs["model"] == "claude-sonnet-4-6"
    blocks = client.messages.last_kwargs["messages"][0]["content"]
    image_blocks = [b for b in blocks if b["type"] == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert image_blocks[0]["source"]["data"]  # base64-encoded, non-empty
    assert "# Lemon Loaf" in md


def test_extract_requires_text_or_image():
    with pytest.raises(ValueError):
        ClaudeExtractor(CONFIG, client=FakeClient(parsed=FULL_DRAFT)).extract()


# --- graceful degradation ---------------------------------------------------


def test_get_extractor_without_key_raises_unavailable():
    no_key = LLMConfig(api_key=None, base_url=None, text_model="x", vision_model="y")
    with pytest.raises(ExtractionUnavailable):
        get_extractor(config=no_key)


def test_api_error_degrades_to_unavailable():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    client = FakeClient(error=err)
    with pytest.raises(ExtractionUnavailable):
        ClaudeExtractor(CONFIG, client=client).extract(text="anything")


def test_none_structured_output_degrades_to_unavailable():
    client = FakeClient(parsed=None)
    with pytest.raises(ExtractionUnavailable):
        ClaudeExtractor(CONFIG, client=client).extract(text="anything")
