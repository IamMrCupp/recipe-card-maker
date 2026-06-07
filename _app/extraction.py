"""LLM extraction service — the shared core for the smart importers (§3.D.1).

One job: turn raw input (pasted text and/or a photo) into a **markdown recipe
draft** in the corpus frontmatter shape, ready to hand to the §C editor as its
`initialMarkdown`. The website (§D.2), photo (§D.3), and social (§D.4) importers
are all thin front-ends to `Extractor.extract`.

Design notes:
  - **Provider-agnostic.** `Extractor` is the seam. `ClaudeExtractor` is the only
    implementation today; a future BYOK / local-model provider drops in here with
    no importer changes (the model/key/base-url already live in `llm_config`).
  - **Structured, then rendered.** The model fills a typed `RecipeDraft` via the
    SDK's structured-output `messages.parse`; we then serialize that to markdown
    deterministically (`render_markdown`). Structured output is far more reliable
    than asking for raw markdown, and lets us leave low-confidence fields *blank*
    for the human rather than fabricating them.
  - **Never crashes the app.** A missing key or an unreachable API raises
    `ExtractionUnavailable`; callers turn that into a clean "unavailable, enter by
    hand" — the §C hand-entry path is entirely independent of this module.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

import anthropic
from pydantic import BaseModel, Field

from _app.llm_config import LLMConfig, load_llm_config

# Output cap for a single recipe draft — generous for ingredients + method, far
# below any timeout concern.
_MAX_TOKENS = 2048


class ExtractionUnavailable(RuntimeError):
    """No provider configured, or the provider was unreachable. Never a crash."""


@dataclass(frozen=True)
class ImageInput:
    """A photo to extract from. `data` is raw bytes; we base64-encode at call time."""

    data: bytes
    media_type: str  # e.g. "image/jpeg", "image/png"


class RecipeDraft(BaseModel):
    """The structured shape the model fills. Every field is optional — anything
    the model isn't confident about comes back empty for the human to complete.
    Never fabricate quantities or steps that aren't present in the source."""

    title: str | None = None
    category: str | None = None
    cuisine: str | None = None
    tags: list[str] = Field(default_factory=list)
    active_time: str | None = None
    total_time: str | None = None
    yield_amount: str | None = None  # rendered to the `yield:` frontmatter key
    difficulty: str | None = None
    notes: str | None = None
    intro: str | None = None  # one short prose paragraph under the title
    ingredients: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class Extractor(Protocol):
    """Raw input -> markdown draft. Implementations raise ExtractionUnavailable
    when they can't reach their backing model."""

    def extract(self, *, text: str | None = None, image: ImageInput | None = None) -> str: ...


EXTRACTION_PROMPT = """\
You extract a single recipe from the supplied content into a structured draft.

Rules:
- Fill only what is clearly present in the source. If a field is missing or you
  are unsure, leave it empty — do NOT guess or fabricate quantities, times, or steps.
- `ingredients`: one item per entry, kept close to the source wording
  (e.g. "200 g all-purpose flour").
- `steps`: the method as an ordered list, one step per entry.
- `intro`: at most one or two sentences of context if the source offers it; else empty.
- `tags`: a few lowercase keywords if obvious; else empty.
- If the content is not a recipe, return an essentially empty draft rather than
  inventing one.
"""


class ClaudeExtractor:
    """`Extractor` backed by the Anthropic API (structured output + vision)."""

    def __init__(self, config: LLMConfig, client: anthropic.Anthropic | None = None) -> None:
        self._config = config
        # The client is injectable so tests run against a recorded response and
        # never touch the network.
        self._client = client or _make_client(config)

    def extract(self, *, text: str | None = None, image: ImageInput | None = None) -> str:
        if text is None and image is None:
            raise ValueError("extract() requires text or image")

        content: list[dict] = [{"type": "text", "text": EXTRACTION_PROMPT}]
        if image is not None:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.standard_b64encode(image.data).decode("ascii"),
                    },
                }
            )
        if text is not None:
            content.append({"type": "text", "text": text})

        # A photo is the dominant signal when present, so it drives model choice.
        model = self._config.vision_model if image is not None else self._config.text_model

        try:
            resp = self._client.messages.parse(
                model=model,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": content}],
                output_format=RecipeDraft,
            )
        except anthropic.APIError as exc:  # connection / timeout / auth / status
            raise ExtractionUnavailable(f"extraction failed: {exc}") from exc

        draft = resp.parsed_output
        if draft is None:
            raise ExtractionUnavailable("model returned no structured output")
        return render_markdown(draft)


def _make_client(config: LLMConfig) -> anthropic.Anthropic:
    kwargs: dict = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return anthropic.Anthropic(**kwargs)


def get_extractor(
    config: LLMConfig | None = None,
    client: anthropic.Anthropic | None = None,
) -> Extractor:
    """Return the configured extractor, or raise ExtractionUnavailable if no key
    is set. The single entry point the importers call."""
    config = config or load_llm_config()
    if not config.configured:
        raise ExtractionUnavailable("LLM extraction is not configured (no API key)")
    return ClaudeExtractor(config, client=client)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

# Full frontmatter key set, in corpus order (matches cakes/erdbeertorte.md and the
# hand-entry STARTER in _web/src/routes/new/+page.svelte). Keys the model doesn't
# fill — source/source_url (the importer sets provenance) and the user-only
# last_made/rating — render blank so the editor presents the complete template.
_FRONTMATTER_KEYS = (
    "title",
    "category",
    "cuisine",
    "source",
    "source_url",
    "tags",
    "active_time",
    "total_time",
    "yield",
    "difficulty",
    "last_made",
    "rating",
    "notes",
)


def _scalar(value: str | None) -> str:
    """Render a scalar frontmatter value for the minimal YAML-ish parser
    (_tools/recipe_parser._parse_frontmatter). Quote values that would otherwise
    confuse it (embedded colon, or a leading '[' that reads as a list)."""
    if not value:
        return ""
    text = value.strip()
    if ":" in text or text.startswith("[") or text.startswith("#"):
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def render_markdown(draft: RecipeDraft) -> str:
    """Serialize a `RecipeDraft` into corpus-shaped recipe markdown.

    Deterministic and side-effect free — the unit-test anchor for the whole
    service. Empty fields render as blank lines/keys for the human to fill.
    """
    values: dict[str, str] = {
        "title": _scalar(draft.title),
        "category": _scalar(draft.category),
        "cuisine": _scalar(draft.cuisine),
        "source": "",
        "source_url": "",
        "tags": "[" + ", ".join(draft.tags) + "]",
        "active_time": _scalar(draft.active_time),
        "total_time": _scalar(draft.total_time),
        "yield": _scalar(draft.yield_amount),
        "difficulty": _scalar(draft.difficulty),
        "last_made": "",
        "rating": "",
        "notes": _scalar(draft.notes),
    }

    lines: list[str] = ["---"]
    lines += [f"{key}: {values[key]}".rstrip() for key in _FRONTMATTER_KEYS]
    lines.append("---")

    title = (draft.title or "").strip()
    lines += ["", f"# {title}".rstrip()]

    if draft.intro and draft.intro.strip():
        lines += ["", draft.intro.strip()]

    lines += ["", "## Yield and timing", ""]
    lines.append(f"- {draft.yield_amount.strip()}" if draft.yield_amount else "-")

    lines += ["", "## Ingredients", ""]
    lines += [f"- {item.strip()}" for item in draft.ingredients] or ["-"]

    lines += ["", "## Method", ""]
    lines += [f"{i}. {step.strip()}" for i, step in enumerate(draft.steps, 1)] or ["1."]

    return "\n".join(lines) + "\n"
