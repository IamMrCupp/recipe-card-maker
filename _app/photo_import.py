"""Photo import (§3.D.3): an image -> a markdown recipe draft for the §C editor.

Thin LLM-only wrapper over the §D.1 extractor's vision path — there is no
structural fallback the way website import has `recipe-scrapers`, so a photo
import simply can't happen without a configured model. A missing key surfaces as
`ImportUnavailable` (reused from §D.2) so the route degrades to "enter by hand".

The uploaded image is used for extraction and then discarded. Retaining it as an
attached recipe image is §3.E (blob storage), not built yet — that's the hook.
"""

from __future__ import annotations

from collections.abc import Callable

from _app.extraction import ExtractionUnavailable, Extractor, ImageInput, get_extractor
from _app.web_import import ImportUnavailable

SOURCE = "photo"

# Accepted upload types (what the Claude vision API supports) and an upload cap.
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — generous for a phone photo


def import_photo(
    data: bytes,
    media_type: str,
    *,
    extractor_factory: Callable[[], Extractor] = get_extractor,
) -> str:
    """Extract a markdown draft from image bytes. Raises ImportUnavailable when
    the LLM isn't configured/reachable (no structural fallback exists)."""
    try:
        return extractor_factory().extract(
            image=ImageInput(data=data, media_type=media_type), source=SOURCE
        )
    except ExtractionUnavailable as exc:
        raise ImportUnavailable(
            "couldn't read that photo and AI import isn't configured — enter it by hand"
        ) from exc
