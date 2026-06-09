"""Website import (§3.D.2): a URL -> a markdown recipe draft for the §C editor.

Two paths, structural first:
  1. **recipe-scrapers (`supported_only=False`)** parses embedded schema.org/Recipe
     data from *any* page that has it (not just the library's hardcoded domains) —
     free, no LLM. Mapped into a `RecipeDraft` and rendered to corpus markdown.
  2. **LLM fallback** (§3.D.1) for pages with no usable schema — the visible page
     text goes through the shared extractor.

Both paths stamp provenance (`source=website`, `source_url=<url>`). If the
structural parse finds nothing *and* the LLM is unavailable, we raise
`ImportUnavailable` so the caller can say "enter by hand" — never a crash.
"""

from __future__ import annotations

from collections.abc import Callable

from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import RecipeScrapersExceptions

from _app.extraction import (
    ExtractionUnavailable,
    Extractor,
    RecipeDraft,
    get_extractor,
    render_markdown,
)
from _app.web_fetch import safe_get

SOURCE = "website"


class ImportUnavailable(RuntimeError):
    """Structural import found no recipe and the LLM fallback is unavailable."""


def _try(fn: Callable[[], object]) -> object | None:
    """Call a scraper field accessor, returning None if the field is absent.
    recipe-scrapers raises on missing fields rather than returning empty."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - any field accessor may raise; absent field -> None
        return None


def _clean_instructions(steps: list[str]) -> list[str]:
    """Drop bare step-label headers some sites emit via `HowToSection` names.

    Such sites (e.g. theunlikelybaker) nest steps under section names ("Combine",
    "Stir", "Chill"), and recipe-scrapers surfaces each name as its own entry right
    before the long step it heads — producing interleaved junk in the draft.

    A header is: a tiny (≤2-word, ≤20-char), punctuation-less entry, immediately
    followed by a step >2× longer **that contains the header's word** (the label is
    the action the step elaborates — "Combine" → "...combine flour..."). That last
    condition is what keeps a real terse step ("Preheat oven" before an unrelated
    step) from being dropped. Conservative either way — the draft is editable."""
    out: list[str] = []
    for i, step in enumerate(steps):
        s = step.strip()
        nxt = steps[i + 1].strip() if i + 1 < len(steps) else ""
        first_word = s.split()[0].lower() if s.split() else ""
        is_label = (
            len(s) <= 20
            and len(s.split()) <= 2
            and not s.endswith((".", "!", "?", ":", ";"))
            and len(nxt) > 40
            and len(nxt) > 2 * len(s)
            and first_word in nxt.lower()  # label heads its own elaboration
        )
        if not is_label:
            out.append(step)
    return out


def _fmt_minutes(minutes: object) -> str | None:
    if not isinstance(minutes, int) or minutes <= 0:
        return None
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h" if hours else f"{mins}m"


def _draft_from_scraper(scraper) -> RecipeDraft:
    """Map recipe-scrapers fields into a RecipeDraft. We deliberately do NOT map
    the scraper's `category` (e.g. "Dessert") onto the corpus `category`, which is
    the folder taxonomy (cakes/cookies/...) — the user assigns the folder in the
    editor. Cuisine + keywords carry over; everything is best-effort."""
    cuisine = _try(scraper.cuisine)
    keywords = _try(scraper.keywords)
    return RecipeDraft(
        title=_try(scraper.title) or None,
        cuisine=cuisine.lower() if isinstance(cuisine, str) else None,
        tags=[k.lower() for k in keywords] if isinstance(keywords, list) else [],
        active_time=_fmt_minutes(_try(scraper.prep_time)),
        total_time=_fmt_minutes(_try(scraper.total_time)),
        yield_amount=_try(scraper.yields) or None,
        intro=_try(scraper.description) or None,
        ingredients=_try(scraper.ingredients) or [],
        steps=_clean_instructions(_try(scraper.instructions_list) or []),
    )


def import_website(url: str, *, extractor_factory: Callable[[], Extractor] = get_extractor) -> str:
    """Fetch `url` and return a corpus-shaped markdown draft. Raises UnsafeURL /
    FetchError (from the fetch) or ImportUnavailable (nothing parsed, no LLM)."""
    html = safe_get(url)

    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
        draft = _draft_from_scraper(scraper)
        if draft.title or draft.ingredients:
            return render_markdown(draft, source_url=url, source=SOURCE)
    except RecipeScrapersExceptions:
        pass  # no schema in wild mode → fall through to the LLM

    try:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        return extractor_factory().extract(text=text, source_url=url, source=SOURCE)
    except ExtractionUnavailable as exc:
        raise ImportUnavailable(
            "couldn't read a recipe from that page and AI import isn't configured — "
            "enter it by hand"
        ) from exc
