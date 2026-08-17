"""SSRF-safe HTTP fetch for website import (§3.D.2).

Fetching a *user-supplied* URL server-side is an SSRF vector: a crafted URL can
point at loopback, the LAN, or a cloud metadata endpoint (169.254.169.254). We
own the fetch (rather than letting recipe-scrapers fetch) precisely so this guard
is unavoidable:

  - scheme allowlist (http/https only),
  - resolve the host and reject any private / loopback / link-local / reserved /
    multicast address,
  - redirects disabled (a public URL can't 30x into an internal one),
  - hard timeout + response-size cap.

Known limitation: resolve-then-fetch leaves a small TOCTOU / DNS-rebinding window
(the resolver could answer differently for the GET than for the check). That's
proportionate for the current localhost/LAN deployment; pinning the validated IP
into the connection is the Phase 3.5 hardening when the app is hosted off-LAN.

**Presenting as a browser.** We ask for public recipe pages the same way a person
reading them would, because a bare `python-httpx/x.y` request gets refused by the
edge WAFs many food sites sit behind. Two things turned out to matter, and both
are needed together — Food Network refuses the full header set over HTTP/1.1 and
serves the page over HTTP/2:

  - a complete Chrome-shaped header set (client hints + `Sec-Fetch-*`, not just a
    `User-Agent` — a lone spoofed UA changed nothing in testing),
  - HTTP/2 (`h2`), so the connection shape matches the headers' story.

We deliberately do NOT go further. Sites behind a Cloudflare *managed challenge*
(the Dotdash Meredith family — allrecipes, seriouseats, simplyrecipes) answer 403
with a JavaScript challenge page; no header or TLS trick clears it without running
a browser engine, and system `curl` is refused identically. Those raise
`BlockedError`, which the importer turns into "this site blocks automated imports,
enter it by hand" rather than a bare network error. We don't impersonate Googlebot
and we don't solve challenges.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
_TIMEOUT_SECONDS = 10.0
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB — recipe pages are small; cap runaway responses
_MAX_REDIRECTS = 5  # real blogs 301 to canonical URLs; follow a few, re-validating each hop

# One coherent Chrome-on-macOS story: UA, client hints, and Sec-Fetch-* all agree,
# and the client below speaks HTTP/2. Bump `_CHROME_MAJOR` when this goes stale —
# the version appears in both the UA string and the `sec-ch-ua` hint.
# `accept-encoding` is deliberately absent: httpx sets what it can actually decode,
# and advertising `br` without brotli installed yields undecodable responses.
_CHROME_MAJOR = "140"
_BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{_CHROME_MAJOR}.0.0.0 Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language": "en-US,en;q=0.9",
    "sec-ch-ua": f'"Chromium";v="{_CHROME_MAJOR}", "Not=A?Brand";v="24", '
    f'"Google Chrome";v="{_CHROME_MAJOR}"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

# Statuses that mean "we know who you are and we're refusing", not "something broke".
_BLOCKED_STATUSES = frozenset({401, 403, 405, 429, 451})


class UnsafeURL(ValueError):
    """The URL's scheme or resolved address is not allowed to be fetched."""


class FetchError(RuntimeError):
    """The page could not be fetched (network error, timeout, bad status, too large)."""


class BlockedError(FetchError):
    """The site refused us as an automated client (bot mitigation / challenge).

    Split out from the generic FetchError so the importer can say something the
    user can act on — hand entry — instead of surfacing a raw status code for a
    page that will never load no matter how many times they retry."""


def _assert_safe(url: str) -> str:
    """Validate scheme + host. Returns the hostname. Raises UnsafeURL."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURL(f"unsupported scheme: {parsed.scheme or '(none)'}")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("missing host")

    # Resolve every A/AAAA record; reject if any is non-public.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURL(f"could not resolve host: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURL(f"refusing to fetch internal address {ip}")
    return host


def safe_get(url: str, *, _client: httpx.Client | None = None) -> str:
    """Fetch `url` and return its HTML, enforcing the SSRF guard. Raises
    UnsafeURL (blocked target), BlockedError (bot mitigation refused us), or
    FetchError (network/status/size/too-many-redirects).

    Redirects are followed manually (`follow_redirects=False`) so that **every hop
    is re-validated** against `_assert_safe` before it's fetched — a public URL
    can't 30x into an internal address. Legitimate http→https / trailing-slash /
    www canonicalization (common on recipe blogs) works. `_client` is injectable
    for tests via httpx.MockTransport; production builds the locked-down client."""
    owns_client = _client is None
    client = _client or httpx.Client(
        follow_redirects=False,
        timeout=_TIMEOUT_SECONDS,
        headers=_BROWSER_HEADERS,
        http2=True,
    )
    try:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            _assert_safe(current)  # validate the original AND every redirect target
            resp = client.get(current)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise FetchError("redirect without a location")
                current = str(resp.url.join(location))  # resolve relative redirects
                continue
            if _is_blocked(resp):
                raise BlockedError(
                    f"{urlparse(current).hostname or 'that site'} blocks automated "
                    f"imports (HTTP {resp.status_code}) — open the page and enter "
                    f"the recipe by hand"
                )
            resp.raise_for_status()
            if len(resp.content) > _MAX_BYTES:
                raise FetchError("response exceeds size limit")
            return resp.text
        raise FetchError("too many redirects")
    except httpx.HTTPError as exc:
        raise FetchError(f"fetch failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()


def _is_blocked(resp: httpx.Response) -> bool:
    """Is this response bot mitigation rather than an ordinary failure?

    `cf-mitigated` is Cloudflare's own marker on a challenge response and is the
    strongest signal; otherwise we go by status. A 404 is NOT treated as blocking
    even though some WAFs use it to hide — we can't distinguish that from a real
    dead link, and telling someone their working URL is bot-blocked is worse than
    telling them it 404'd."""
    return "cf-mitigated" in resp.headers or resp.status_code in _BLOCKED_STATUSES
