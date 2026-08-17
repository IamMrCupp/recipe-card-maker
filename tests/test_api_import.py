"""Tests for website import (§3.D.2): SSRF guard, structural + LLM-fallback
import logic, route status mapping, and the provenance round-trip.

No network and no live API: the SSRF guard is exercised against IP-literal URLs,
`safe_get` is monkeypatched to serve fixture HTML, and the LLM fallback uses a
fake extractor.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from recipe_parser import parse_recipe_text

from _app import web_fetch, web_import
from _app.extraction import ExtractionUnavailable
from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore
from _app.web_fetch import BlockedError, FetchError, UnsafeURL, _assert_safe, safe_get

JSONLD_PAGE = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Test Lemon Loaf",
"recipeCuisine":"American","recipeCategory":"Dessert",
"keywords":"lemon, quickbread","totalTime":"PT1H10M","recipeYield":"1 loaf",
"description":"A bright simple loaf.","recipeIngredient":["200 g flour","2 lemons, zested"],
"recipeInstructions":[{"@type":"HowToStep","text":"Mix."},{"@type":"HowToStep","text":"Bake."}]}
</script></head><body>x</body></html>"""

NO_SCHEMA_PAGE = "<html><body><p>just a blog post, no recipe schema</p></body></html>"


# --- SSRF guard -------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/r",
        "http://localhost/r",
        "http://10.0.0.1/r",
        "http://192.168.1.1/r",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://[::1]/r",
    ],
)
def test_assert_safe_rejects_internal(url):
    with pytest.raises(UnsafeURL):
        _assert_safe(url)


def test_assert_safe_rejects_non_http_scheme():
    with pytest.raises(UnsafeURL):
        _assert_safe("ftp://example.com/r")
    with pytest.raises(UnsafeURL):
        _assert_safe("file:///etc/passwd")


def test_safe_get_rejects_bad_scheme_before_any_request():
    # public IP literal passes the address check; scheme check fails first for ftp
    with pytest.raises(UnsafeURL):
        safe_get("ftp://93.184.216.34/r")


def test_assert_safe_allows_public_ip_literal():
    # a public address passes the guard (no fetch happens in _assert_safe)
    assert _assert_safe("https://93.184.216.34/recipe") == "93.184.216.34"


# --- redirect following (public-IP-literal URLs so no real DNS happens) ------


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_safe_get_follows_redirect_to_public_target():
    def handler(request):
        if request.url.path == "/r":
            return httpx.Response(301, headers={"location": "https://93.184.216.34/final"})
        return httpx.Response(200, text="<html>final page</html>")

    html = safe_get("https://93.184.216.34/r", _client=_mock_client(handler))
    assert "final page" in html


def test_safe_get_blocks_redirect_to_internal_target():
    # a public URL that 30x's into a loopback address must be rejected at the hop
    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/latest/meta-data"})

    with pytest.raises(UnsafeURL):
        safe_get("https://93.184.216.34/r", _client=_mock_client(handler))


def test_safe_get_caps_redirect_chain():
    def handler(request):
        # always redirect onward → exceed the hop cap
        return httpx.Response(301, headers={"location": "https://93.184.216.34/again"})

    with pytest.raises(FetchError, match="too many redirects"):
        safe_get("https://93.184.216.34/start", _client=_mock_client(handler))


# --- bot mitigation ---------------------------------------------------------


def test_browser_headers_present_and_self_consistent():
    # A lone spoofed UA changed nothing in testing; the client-hint + Sec-Fetch-*
    # set is what moved sites. Guard the whole set, and keep the advertised Chrome
    # version identical across the UA string and the client hint.
    headers = web_fetch._BROWSER_HEADERS
    for key in ("user-agent", "accept", "accept-language", "sec-ch-ua", "sec-fetch-mode"):
        assert key in headers
    assert f"Chrome/{web_fetch._CHROME_MAJOR}" in headers["user-agent"]
    assert f'"{web_fetch._CHROME_MAJOR}"' in headers["sec-ch-ua"]
    # brotli isn't installed; advertising `br` would yield undecodable bodies
    assert "accept-encoding" not in headers


@pytest.mark.parametrize("status", [401, 403, 429, 451])
def test_safe_get_reports_refusal_as_blocked(status):
    def handler(request):
        return httpx.Response(status, text="<html>Access Denied</html>")

    with pytest.raises(BlockedError, match="blocks automated imports"):
        safe_get("https://93.184.216.34/r", _client=_mock_client(handler))


def test_safe_get_flags_cloudflare_challenge_by_header():
    # the Dotdash Meredith case: a JS challenge page marked by `cf-mitigated`
    def handler(request):
        return httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="<html>js</html>")

    with pytest.raises(BlockedError):
        safe_get("https://93.184.216.34/r", _client=_mock_client(handler))


def test_safe_get_leaves_404_as_an_ordinary_failure():
    # a dead link must not be reported as bot-blocking — that misdirects the fix
    def handler(request):
        return httpx.Response(404, text="not found")

    with pytest.raises(FetchError) as exc:
        safe_get("https://93.184.216.34/r", _client=_mock_client(handler))
    assert not isinstance(exc.value, BlockedError)


# --- instruction-label cleanup (§D.2, from on-device ube-crinkles import) ----


def test_clean_instructions_drops_section_labels():
    # the theunlikelybaker pattern: HowToSection names emitted as their own steps
    raw = [
        "Combine",
        "In a medium bowl, combine flour, baking powder and salt. Set aside.",
        "Chill",
        "Cover the bowl with cling wrap and chill in the fridge for at least 4 hours.",
    ]
    cleaned = web_import._clean_instructions(raw)
    assert cleaned == [
        "In a medium bowl, combine flour, baking powder and salt. Set aside.",
        "Cover the bowl with cling wrap and chill in the fridge for at least 4 hours.",
    ]


def test_clean_instructions_keeps_real_terse_step():
    # "Preheat oven" is a real step (its word isn't echoed in the next, unrelated step)
    raw = ["Preheat oven", "Mix the dry ingredients in a large bowl until evenly combined."]
    assert web_import._clean_instructions(raw) == raw


def test_clean_instructions_no_op_on_normal_steps():
    raw = ["Cream butter and sugar.", "Fold in flour and bake at 175C for 50 minutes."]
    assert web_import._clean_instructions(raw) == raw


# --- keyword/tag normalization (§D.2) ---------------------------------------


def test_normalize_keywords_splits_kingarthur_double_semicolons():
    # the reported bug, verbatim from kingarthurbaking.com: recipe-scrapers splits
    # `keywords` on commas only, so this arrived as ONE tag with `;;` inside it
    raw = ["Layer cake;;Chocolate;;Vanilla;;Celebrations"]
    assert web_import._normalize_keywords(raw) == [
        "layer cake",
        "chocolate",
        "vanilla",
        "celebrations",
    ]


@pytest.mark.parametrize(
    "raw",
    [
        ["a;;b"],
        ["a; b"],
        ["a|b"],
        ["a / b"],
        ["a, b"],
        ["a,b"],
        "a;;b",  # a bare string, not a list
    ],
)
def test_normalize_keywords_handles_each_separator(raw):
    assert web_import._normalize_keywords(raw) == ["a", "b"]


def test_normalize_keywords_drops_cms_metadata_pairs():
    # delish/Hearst dumps internal CMS fields into keywords
    raw = [
        "contentId: 13efd1a8-d0cf-4a90-9120-16674375dd12",
        "TOTALTIME: 00:45:00",
        "sponsored: false",
        "dinner",
        "creamy chicken",
    ]
    assert web_import._normalize_keywords(raw) == ["dinner", "creamy chicken"]


def test_normalize_keywords_dedupes_case_insensitively_keeping_order():
    assert web_import._normalize_keywords(["Cake", "cake", "Bread"]) == ["cake", "bread"]


def test_normalize_keywords_tolerates_absent_or_odd_input():
    assert web_import._normalize_keywords(None) == []
    assert web_import._normalize_keywords([]) == []
    assert web_import._normalize_keywords(["", "  ", ";;"]) == []


def test_normalized_tags_render_into_the_draft_frontmatter(monkeypatch):
    # end-to-end: the `;;` never reaches the markdown the editor opens
    page = JSONLD_PAGE.replace(
        '"keywords":"lemon, quickbread"', '"keywords":"Layer cake;;Chocolate;;Vanilla"'
    )
    monkeypatch.setattr(web_import, "safe_get", lambda url: page)
    markdown = web_import.import_website("https://example.com/r")

    assert "tags: [layer cake, chocolate, vanilla]" in markdown
    assert ";;" not in markdown
    assert parse_recipe_text(markdown).meta["tags"] == ["layer cake", "chocolate", "vanilla"]


# --- import logic -----------------------------------------------------------


def test_import_website_structural_path(monkeypatch):
    monkeypatch.setattr(web_import, "safe_get", lambda url: JSONLD_PAGE)
    md = web_import.import_website("https://example.com/lemon-loaf")

    assert "title: Test Lemon Loaf" in md
    assert "source: website" in md
    assert "source_url: https://example.com/lemon-loaf" in md
    assert "cuisine: american" in md  # lowercased
    assert "total_time: 1h 10m" in md  # minutes -> formatted
    assert "- 200 g flour" in md
    assert "1. Mix." in md
    # corpus `category` left blank — folder taxonomy is the user's choice
    assert "\ncategory: \n" in md or "\ncategory:\n" in md
    assert parse_recipe_text(md).title == "Test Lemon Loaf"


class _FakeExtractor:
    def __init__(self):
        self.last = None

    def extract(self, *, text=None, image=None, source_url=None, source=None):
        self.last = {"text": text, "source_url": source_url, "source": source}
        from _app.extraction import RecipeDraft, render_markdown

        return render_markdown(
            RecipeDraft(title="From LLM", ingredients=["1 egg"]),
            source_url=source_url,
            source=source,
        )


def test_import_website_falls_back_to_llm(monkeypatch):
    monkeypatch.setattr(web_import, "safe_get", lambda url: NO_SCHEMA_PAGE)
    fake = _FakeExtractor()
    md = web_import.import_website("https://blog.example/post", extractor_factory=lambda: fake)

    assert "title: From LLM" in md
    assert "source_url: https://blog.example/post" in md
    assert fake.last["source"] == "website"
    assert "just a blog post" in fake.last["text"]  # visible text was passed


def test_import_website_unavailable_when_no_schema_and_no_llm(monkeypatch):
    monkeypatch.setattr(web_import, "safe_get", lambda url: NO_SCHEMA_PAGE)

    def _no_llm():
        raise ExtractionUnavailable("no key")

    with pytest.raises(web_import.ImportUnavailable):
        web_import.import_website("https://blog.example/post", extractor_factory=_no_llm)


# --- route ------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    return TestClient(create_app(store))


def test_route_empty_url_422(client):
    assert client.post("/api/import/website", json={"url": "  "}).status_code == 422


def test_route_maps_exceptions(client, monkeypatch):
    import _app.main as main
    from _app.web_fetch import FetchError

    monkeypatch.setattr(
        main, "import_website", lambda url: (_ for _ in ()).throw(UnsafeURL("nope"))
    )
    assert client.post("/api/import/website", json={"url": "http://x/r"}).status_code == 400

    monkeypatch.setattr(
        main, "import_website", lambda url: (_ for _ in ()).throw(FetchError("boom"))
    )
    assert client.post("/api/import/website", json={"url": "http://x/r"}).status_code == 502

    monkeypatch.setattr(
        main,
        "import_website",
        lambda url: (_ for _ in ()).throw(web_import.ImportUnavailable("hand")),
    )
    assert client.post("/api/import/website", json={"url": "http://x/r"}).status_code == 503


def test_route_success_returns_markdown(client, monkeypatch):
    import _app.main as main

    monkeypatch.setattr(web_import, "safe_get", lambda url: JSONLD_PAGE)
    monkeypatch.setattr(main, "import_website", web_import.import_website)
    resp = client.post("/api/import/website", json={"url": "https://example.com/r"})
    assert resp.status_code == 200
    assert "title: Test Lemon Loaf" in resp.json()["markdown"]


def test_imported_recipe_saves_with_website_provenance(client, monkeypatch):
    """The two provenance channels meet: source_url rides in the markdown
    frontmatter, source=website is set on save. (Open question #4 in the plan.)"""
    import _app.main as main

    monkeypatch.setattr(web_import, "safe_get", lambda url: JSONLD_PAGE)
    monkeypatch.setattr(main, "import_website", web_import.import_website)

    draft = client.post("/api/import/website", json={"url": "https://example.com/r"}).json()
    created = client.post(
        "/api/recipes",
        json={"markdown": draft["markdown"], "source": "website", "category": "cakes"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source"] == "website"
    assert body["source_url"] == "https://example.com/r"
