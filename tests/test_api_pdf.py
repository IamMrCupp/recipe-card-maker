"""Tests for the PDF download endpoints (§3.B.3).

Each endpoint renders a stored recipe through the existing reportlab builders
and streams it back.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from _app.main import create_app
from _app.sqlite_store import SQLiteRecipeStore
from _app.storage import Provenance

CAKE_MD = """---
title: Erdbeertorte
category: cakes
tags: [strawberry]
---
# Erdbeertorte

A strawberry cake.

## Yield and timing
- 8 servings

## Biskuit
### Ingredients
- 4 eggs
- 120 g sugar
### Method
1. Whisk the eggs.
2. Fold in the sugar.
"""


@pytest.fixture
def client(tmp_path):
    store = SQLiteRecipeStore(db_path=tmp_path / "test.db")
    rid = store.create(CAKE_MD, source=Provenance.IMPORT, rel_path="cakes/erdbeertorte.md").id
    return TestClient(create_app(store)), rid


@pytest.mark.parametrize("kind", ["card", "letter"])
def test_pdf_endpoint_returns_valid_pdf(client, kind):
    api, rid = client
    resp = api.get(f"/api/recipes/{rid}/{kind}.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 500  # a real document, not an empty shell
    assert "erdbeertorte" in resp.headers["content-disposition"]


@pytest.mark.parametrize("kind", ["card", "letter"])
def test_pdf_unknown_id_404(client, kind):
    api, _ = client
    assert api.get(f"/api/recipes/nope/{kind}.pdf").status_code == 404


def test_card_and_letter_differ(client):
    api, rid = client
    card = api.get(f"/api/recipes/{rid}/card.pdf").content
    letter = api.get(f"/api/recipes/{rid}/letter.pdf").content
    assert card[:5] == b"%PDF-" and letter[:5] == b"%PDF-"
    assert card != letter  # different page sizes / layouts
