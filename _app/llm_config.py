"""Configuration for the LLM extraction service (§3.D.1).

Extraction is *optional*: the app boots, browses, and hand-enters recipes with
no LLM configured at all. These settings only come into play when one of the
smart importers (§3.D.2–D.4) tries to turn raw input into a draft.

Everything is read from the environment so the model is a deployment choice, not
a code change. That same indirection is what lets a future public release point
at a self-hosted / local model (`RCM_LLM_BASE_URL`) or have each user bring their
own key, without touching the importers.

Model defaults: the `claude-api` guidance defaults to Opus, but extraction is a
single-shot structured task that doesn't need it — we deliberately pick the
cheaper tiers (Haiku for text, Sonnet for vision) to keep per-import cost low for
personal use now and at public scale later. Override via env if you want more.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TEXT_MODEL = "claude-haiku-4-5"
DEFAULT_VISION_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class LLMConfig:
    """Resolved extraction settings. `api_key` is None when unconfigured."""

    api_key: str | None
    base_url: str | None
    text_model: str
    vision_model: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def load_llm_config() -> LLMConfig:
    """Read extraction config from the environment.

    `RCM_LLM_API_KEY` takes precedence; `ANTHROPIC_API_KEY` is the conventional
    fallback so an existing Anthropic environment works with no extra setup.
    """
    api_key = os.environ.get("RCM_LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    return LLMConfig(
        api_key=api_key or None,
        base_url=os.environ.get("RCM_LLM_BASE_URL") or None,
        text_model=os.environ.get("RCM_LLM_TEXT_MODEL", DEFAULT_TEXT_MODEL),
        vision_model=os.environ.get("RCM_LLM_VISION_MODEL", DEFAULT_VISION_MODEL),
    )


def extraction_available() -> bool:
    """Whether smart import can be offered. Importers and (later) the UI gate on this."""
    return load_llm_config().configured
