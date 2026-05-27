"""Build-time helpers shared by the PDF generators.

Kept separate from recipe parsing so the output-reproducibility concern lives in
one place. The leading underscore keeps this module out of find_recipes()'s walk
(see recipe_parser.find_recipes).
"""

from __future__ import annotations

import os

# Stable anchor so generated PDFs are byte-reproducible. ReportLab stamps
# /CreationDate, /ModDate, and the document /ID from SOURCE_DATE_EPOCH when it is
# set; without it, every `make pdfs` rewrites those bytes and the committed PDFs
# churn on each build (and byte-comparison in tests becomes impossible).
#
# 2024-01-01T00:00:00Z — an arbitrary fixed point. Override by exporting
# SOURCE_DATE_EPOCH (e.g. in CI) if you ever want the real build time embedded.
_DEFAULT_SOURCE_DATE_EPOCH = "1704067200"


def ensure_reproducible_pdf_dates() -> None:
    """Pin SOURCE_DATE_EPOCH (only if unset) so ReportLab output is deterministic.

    Idempotent — safe to call on every PDF build. Honors an existing
    SOURCE_DATE_EPOCH so CI or a curious user can override the embedded date.
    """
    os.environ.setdefault("SOURCE_DATE_EPOCH", _DEFAULT_SOURCE_DATE_EPOCH)
