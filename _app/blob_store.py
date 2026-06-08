"""Local image blob store for recipe images (§3.E.1).

The DB holds image *refs* (`StoredRecipe.images`); the bytes live here, in a
gitignored `_media/` dir (underscore prefix = invisible to the recipe build, like
`_app`/`_web`). These are the full-quality originals; export (§3.A.3) materializes
downsized web copies into a *committed* `images/` dir separately.

A ref is `<uuid-hex>.<ext>` — opaque, collision-free, and validated on every read
so a crafted ref can't escape the media dir (path traversal).
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEDIA_DIR = REPO_ROOT / "_media"

# Accepted upload types ↔ on-disk extension (jpg canonicalizes image/jpeg).
_EXT_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
_TYPE_BY_EXT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
_REF_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|gif)$")


def default_media_dir() -> Path:
    """The media dir, overridable via env (tests point it at a tmp dir)."""
    return Path(os.environ.get("RCM_MEDIA_DIR", DEFAULT_MEDIA_DIR))


class BlobStore:
    """Content store for image bytes under a media dir. Injected like RecipeStore."""

    def __init__(self, media_dir: Path | None = None) -> None:
        self.media_dir = Path(media_dir) if media_dir is not None else default_media_dir()

    def put(self, data: bytes, content_type: str) -> str:
        """Store bytes, returning a new ref. Raises ValueError on unsupported type."""
        ext = _EXT_BY_TYPE.get(content_type)
        if ext is None:
            raise ValueError(f"unsupported image type: {content_type}")
        self.media_dir.mkdir(parents=True, exist_ok=True)
        ref = f"{uuid.uuid4().hex}.{ext}"
        (self.media_dir / ref).write_bytes(data)
        return ref

    def path(self, ref: str) -> Path:
        """Resolve a ref to its on-disk path. Raises ValueError on a malformed ref."""
        if not _REF_RE.match(ref):
            raise ValueError("bad image ref")
        return self.media_dir / ref

    def content_type(self, ref: str) -> str:
        return _TYPE_BY_EXT[ref.rsplit(".", 1)[-1]]

    def delete(self, ref: str) -> None:
        """Remove a blob if present. No-op on a malformed or missing ref."""
        if _REF_RE.match(ref):
            (self.media_dir / ref).unlink(missing_ok=True)
