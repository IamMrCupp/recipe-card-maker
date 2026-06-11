"""Tests for the single-user auth gate (Phase 4α).

Auth engages only when RCM_AUTH_PASSWORD is set; without it every route behaves
exactly as before (the entire pre-4α suite is the regression net for that mode).
TestClient uses an https base_url so the `secure` session cookie round-trips.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app import auth
from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore

RECIPE_MD = """---
title: Lemon Loaf
category: cakes
---
# Lemon Loaf

## Ingredients
- 1 lemon
"""

PASSWORD = "correct horse"
TOKEN = "native-client-token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RCM_AUTH_PASSWORD", PASSWORD)
    monkeypatch.setenv("RCM_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("RCM_SESSION_SECRET", "test-secret")
    auth.reset_lockouts()
    store = SQLiteRecipeStore(db_path=tmp_path / "t.db")
    return TestClient(create_app(store), base_url="https://testserver")


@pytest.fixture
def open_client(tmp_path):
    """Auth disabled (no RCM_AUTH_PASSWORD) — local-dev mode."""
    store = SQLiteRecipeStore(db_path=tmp_path / "t.db")
    return TestClient(create_app(store), base_url="https://testserver")


# --- disabled mode ------------------------------------------------------------


def test_auth_disabled_everything_open(open_client):
    assert open_client.get("/api/recipes").status_code == 200
    me = open_client.get("/api/auth/me").json()
    assert me == {"auth_enabled": False, "authenticated": True}


# --- the gate -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/recipes"),
        ("GET", "/api/search?q=x"),
        ("POST", "/api/recipes"),
        ("POST", "/api/import/website"),
        ("POST", "/api/import/photo"),
        ("POST", "/api/import/social"),
        ("GET", "/api/import/capabilities"),
        ("GET", "/api/recipes/xyz/card.pdf"),
        ("GET", "/api/images/deadbeef.jpg"),
    ],
)
def test_gated_routes_401_without_credentials(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_and_shell_stay_open(client):
    assert client.get("/health").status_code == 200
    # SPA shell (no build dir in tests → API-only mode returns 404, not 401)
    assert client.get("/some/page").status_code in (200, 404)


# --- login flow ---------------------------------------------------------------


def test_login_wrong_password_401(client):
    resp = client.post("/api/auth/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_sets_cookie_and_unlocks_api(client):
    resp = client.post("/api/auth/login", json={"password": PASSWORD})
    assert resp.status_code == 204
    assert auth.SESSION_COOKIE in resp.cookies
    # cookie jar persists on the TestClient → API now reachable
    assert client.get("/api/recipes").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me == {"auth_enabled": True, "authenticated": True}


def test_logout_clears_session(client):
    client.post("/api/auth/login", json={"password": PASSWORD})
    assert client.get("/api/recipes").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/recipes").status_code == 401


def test_lockout_after_repeated_failures(client):
    for _ in range(auth.LOCKOUT_THRESHOLD):
        assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    # locked now — even the right password is refused
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429


def test_tampered_cookie_rejected(client):
    client.cookies.set(auth.SESSION_COOKIE, "9999999999.deadbeef")
    assert client.get("/api/recipes").status_code == 401


# --- bearer token (the 4β native-client path) ----------------------------------


def test_bearer_token_accepted(client):
    resp = client.get("/api/recipes", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200


def test_wrong_bearer_rejected(client):
    resp = client.get("/api/recipes", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
