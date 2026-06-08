"""Social-media paste import (§3.D.4): pasted caption/post text -> a markdown
recipe draft for the §C editor.

Deliberately paste-only — we do NOT auto-fetch post URLs or transcribe video
(both deferred per plan.md). Like photo import, this is LLM-only: there's no
structural fallback, so a missing key surfaces as `ImportUnavailable` (reused
from §D.2) and the route degrades to "enter by hand".
"""

from __future__ import annotations

from collections.abc import Callable

from _app.extraction import ExtractionUnavailable, Extractor, get_extractor
from _app.web_import import ImportUnavailable

SOURCE = "social"


def import_social(
    text: str,
    *,
    extractor_factory: Callable[[], Extractor] = get_extractor,
) -> str:
    """Extract a markdown draft from pasted text. Raises ImportUnavailable when
    the LLM isn't configured/reachable (no structural fallback exists)."""
    try:
        return extractor_factory().extract(text=text, source=SOURCE)
    except ExtractionUnavailable as exc:
        raise ImportUnavailable(
            "couldn't read a recipe from that text and AI import isn't configured — "
            "enter it by hand"
        ) from exc
