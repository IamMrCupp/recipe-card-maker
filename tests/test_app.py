"""Smoke tests for the app backend (_app/).

Phase 3 §3.A.1 — confirms the FastAPI app boots and the health endpoint
responds. Read/write endpoints get their own tests as they land.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from _app.main import create_app


def test_health_ok():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_app_factory_is_independent():
    # create_app() should yield a fresh app each call (no shared mutable state).
    assert create_app() is not create_app()
