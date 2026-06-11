"""Single-user authentication for the hosted home base (Phase 4α).

Design (see plan-host-homebase.md):
  - **Disabled by default.** Auth only engages when ``RCM_AUTH_PASSWORD`` is set —
    local ``make serve`` and the test suite run exactly as before.
  - Two credentials are accepted on gated routes: a **signed session cookie**
    (browser login) or a **static bearer token** ``RCM_AUTH_TOKEN`` (the future
    native clients, 4β+).
  - The static SPA shell stays public by design — it contains no recipe data and
    the service worker must precache it without credentials. Everything
    data-bearing lives under ``/api`` and is gated here.
  - In-memory per-IP lockout on the login endpoint (single replica, so
    process-local state is the truth).

No new dependencies: the session cookie is a stdlib HMAC over an expiry stamp.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "rcm_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 days
LOCKOUT_THRESHOLD = 5  # failed attempts ...
LOCKOUT_SECONDS = 60  # ... lock this long

# Routes under /api that must work without credentials.
_OPEN_PATHS = frozenset({"/api/auth/login", "/api/auth/me"})


@dataclass(frozen=True)
class AuthConfig:
    password: str | None
    token: str | None
    session_secret: str

    @property
    def enabled(self) -> bool:
        return bool(self.password)


def auth_config() -> AuthConfig:
    """Read auth settings from the environment (cheap; read per use so tests and
    container restarts pick changes up without import-order games)."""
    password = os.environ.get("RCM_AUTH_PASSWORD") or None
    return AuthConfig(
        password=password,
        token=os.environ.get("RCM_AUTH_TOKEN") or None,
        # Falling back to the password keeps misconfiguration (password set,
        # secret forgotten) safe-but-working; sessions just reset on rotation.
        session_secret=os.environ.get("RCM_SESSION_SECRET") or password or "dev-insecure",
    )


# ---------------------------------------------------------------------------
# Session cookie: "<expires>.<hmac(secret, expires)>"
# ---------------------------------------------------------------------------


def _sign(secret: str, expires: int) -> str:
    mac = hmac.new(secret.encode(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{mac}"


def make_session_value(cfg: AuthConfig, now: float | None = None) -> str:
    expires = int(now or time.time()) + SESSION_TTL_SECONDS
    return _sign(cfg.session_secret, expires)


def session_valid(cfg: AuthConfig, value: str | None, now: float | None = None) -> bool:
    if not value or "." not in value:
        return False
    expires_str, _, _mac = value.partition(".")
    try:
        expires = int(expires_str)
    except ValueError:
        return False
    if expires < (now or time.time()):
        return False
    return hmac.compare_digest(value, _sign(cfg.session_secret, expires))


# ---------------------------------------------------------------------------
# Login rate limiting (per-IP, in-memory — correct for the 1-replica deploy)
# ---------------------------------------------------------------------------

_failures: dict[str, tuple[int, float]] = {}  # ip -> (consecutive fails, locked_until)


def _client_ip(request: Request) -> str:
    # Behind ingress-nginx the client address arrives in X-Forwarded-For; locally
    # it's the socket peer. First hop of the header is the real client.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _locked(ip: str, now: float) -> bool:
    fails, until = _failures.get(ip, (0, 0.0))
    return fails >= LOCKOUT_THRESHOLD and now < until


def _record_failure(ip: str, now: float) -> None:
    fails, _ = _failures.get(ip, (0, 0.0))
    _failures[ip] = (fails + 1, now + LOCKOUT_SECONDS)


def _clear_failures(ip: str) -> None:
    _failures.pop(ip, None)


def reset_lockouts() -> None:
    """Test hook: clear the in-memory lockout table."""
    _failures.clear()


# ---------------------------------------------------------------------------
# The gate + login handlers (wired into the /api router in main.py)
# ---------------------------------------------------------------------------


def require_auth(request: Request) -> None:
    """Router dependency: allow when auth is disabled, the path is an auth
    endpoint, a valid bearer token is presented, or the session cookie checks out."""
    cfg = auth_config()
    if not cfg.enabled:
        return
    if request.url.path in _OPEN_PATHS:
        return
    authz = request.headers.get("authorization", "")
    if cfg.token and hmac.compare_digest(authz, f"Bearer {cfg.token}"):
        return
    if session_valid(cfg, request.cookies.get(SESSION_COOKIE)):
        return
    raise HTTPException(status_code=401, detail="login required")


def login(request: Request, password: str, response: Response) -> None:
    """Validate the password and set the session cookie. 401 wrong, 429 locked."""
    cfg = auth_config()
    if not cfg.enabled:
        return  # auth disabled — login is a no-op success so the UI can't wedge
    now = time.time()
    ip = _client_ip(request)
    if _locked(ip, now):
        raise HTTPException(status_code=429, detail="too many attempts — try again later")
    if not hmac.compare_digest(password, cfg.password):
        _record_failure(ip, now)
        raise HTTPException(status_code=401, detail="wrong password")
    _clear_failures(ip)
    response.set_cookie(
        SESSION_COOKIE,
        make_session_value(cfg),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def status(request: Request) -> dict:
    """Session probe for the frontend: distinguishes auth-off / authed / not."""
    cfg = auth_config()
    if not cfg.enabled:
        return {"auth_enabled": False, "authenticated": True}
    return {
        "auth_enabled": True,
        "authenticated": session_valid(cfg, request.cookies.get(SESSION_COOKIE)),
    }
