# Recipes

A personal recipe collection. Markdown is the source of truth; PDFs (full-page letter for kitchen binders, 4×6 for the recipe tin) are generated artifacts.

**2 recipes** across **2 categories**

## Quick links

- [Cookies](#cookies) (1)
- [Cakes & Tortes](#cakes--tortes) (1)

## Cookies

| Recipe | Cuisine | Difficulty | Active time | Rating | PDFs |
| --- | --- | --- | --- | --- | --- |
| [Sun and Moon Cookies](cookies/sun_and_moon.md) | German | medium | 45m | — | [letter](cookies/sun_and_moon_full.pdf) · [4×6](cookies/sun_and_moon_4x6.pdf) |

## Cakes & Tortes

| Recipe | Cuisine | Difficulty | Active time | Rating | PDFs |
| --- | --- | --- | --- | --- | --- |
| [Erdbeertorte](cakes/erdbeertorte.md) | German | medium | 1h | — | [letter](cakes/erdbeertorte_full.pdf) · [4×6](cakes/erdbeertorte_4x6.pdf) |

## Tags

`konditorei` (2) · `strawberry` (1) · `biskuit` (1) · `pastry_cream` (1) · `summer` (1) · `tortenguss` (1) · `marzipan` (1) · `shortbread` (1) · `jam` (1) · `christmas` (1) · `spitzbuben` (1)

## Working with this repo

First-time setup (needs Python 3.14 — see `.python-version`). Create a virtualenv and install the pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then, with the venv active:

```bash
# rebuild all PDFs
make

# rebuild just one recipe
python _tools/make_full_pdf.py cookies/sun_and_moon.md
python _tools/make_cards_pdf.py cookies/sun_and_moon.md

# regenerate this README
python _tools/update_readme.py
```

To add a new recipe, copy `_templates/recipe_full.md` into the appropriate category folder, fill in the frontmatter and body, then `make`.
