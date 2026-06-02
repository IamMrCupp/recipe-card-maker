"""Shared style constants and inline-markdown helper for the PDF builders.

Color palette and the small markdown-to-ReportLab-inline-tag converter live here
so the two PDF generators (`make_full_pdf`, `make_cards_pdf`) don't drift apart.
The per-file `STYLES` (ParagraphStyle) dicts intentionally stay local — they
differ between letter-size and 4×6 card layouts.

The leading underscore keeps this module out of `recipe_parser.find_recipes()`'s
walk (see the underscore-prefix rule there).
"""

from __future__ import annotations

import re

from reportlab.lib.colors import HexColor

# --- Color palette ----------------------------------------------------------

ACCENT = HexColor("#8B2E2E")  # deep red — title, section headings
INK = HexColor("#2A2118")  # body text
SOFT = HexColor("#6B5D4F")  # subtitles, meta lines, footnotes
RULE = HexColor("#C9B8A2")  # horizontal rules

# --- Inline markdown -> ReportLab inline tags -------------------------------

_MD_TOKEN_RE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|`[^`]+`)")


def md_inline(text: str) -> str:
    """Convert a small subset of inline markdown to ReportLab inline tags.

    Supports `**bold**`, `__bold__`, `*italic*`, `_italic_`, `` `code` ``.
    """

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok.startswith("**") or tok.startswith("__"):
            return f"<b>{tok[2:-2]}</b>"
        if tok.startswith("*") or tok.startswith("_"):
            return f"<i>{tok[1:-1]}</i>"
        if tok.startswith("`"):
            return f"<font face='Courier'>{tok[1:-1]}</font>"
        return tok

    return _MD_TOKEN_RE.sub(sub, text)
