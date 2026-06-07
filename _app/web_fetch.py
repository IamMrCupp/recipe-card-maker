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
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
_TIMEOUT_SECONDS = 10.0
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB — recipe pages are small; cap runaway responses
_USER_AGENT = "recipe-card-maker/0.1 (+website-import)"


class UnsafeURL(ValueError):
    """The URL's scheme or resolved address is not allowed to be fetched."""


class FetchError(RuntimeError):
    """The page could not be fetched (network error, timeout, bad status, too large)."""


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


def safe_get(url: str) -> str:
    """Fetch `url` and return its HTML, enforcing the SSRF guard. Raises
    UnsafeURL (blocked target) or FetchError (network/status/size)."""
    _assert_safe(url)
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=_TIMEOUT_SECONDS,
            headers={"user-agent": _USER_AGENT},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) > _MAX_BYTES:
                raise FetchError("response exceeds size limit")
            return resp.text
    except httpx.HTTPError as exc:
        raise FetchError(f"fetch failed: {exc}") from exc
