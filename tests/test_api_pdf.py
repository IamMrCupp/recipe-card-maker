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


def _mediabox_inches(pdf: bytes) -> tuple[float, float]:
    import re

    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", pdf)
    return float(m.group(1)) / 72, float(m.group(2)) / 72


def test_landscape_card_is_6x4(client):
    api, rid = client
    portrait = api.get(f"/api/recipes/{rid}/card.pdf")
    landscape = api.get(f"/api/recipes/{rid}/card-landscape.pdf")
    assert landscape.status_code == 200
    assert landscape.content[:5] == b"%PDF-"
    assert "landscape" in landscape.headers["content-disposition"]

    pw, ph = _mediabox_inches(portrait.content)
    lw, lh = _mediabox_inches(landscape.content)
    assert (round(pw), round(ph)) == (4, 6)  # portrait unchanged
    assert (round(lw), round(lh)) == (6, 4)  # landscape rotated


def test_landscape_unknown_id_404(client):
    api, _ = client
    assert api.get("/api/recipes/nope/card-landscape.pdf").status_code == 404
