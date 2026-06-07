# `_app/` — recipe app backend (Phase 3)

The cross-platform recipe app: capture recipes (by hand, website, photo,
social), store them, browse/search, and print recipe cards. See the project
plan (`plan.md` Phase 3) and `phase-3-checklist.md` for the full roadmap.

## Why the leading underscore

The repo treats any `_`-prefixed top-level directory as **build-invisible
machinery** — both `recipe_parser.find_recipes()` and the `Makefile`'s `find`
skip them, which is how `_tools/` and `_templates/` stay out of the recipe
index and PDF build. The backend is machinery, not recipe content, so it lives
under `_app/` for the same reason. (Considered teaching the scanner an explicit
category allowlist instead; the underscore convention is simpler, already
enforced in two places, and reversible — revisit if it grates.)

## Architecture invariants (Phase 3)

1. **The database is the source of truth; markdown + PDF are export formats.**
2. **The hand-entry editor is the spine** — every importer produces a *draft*
   that the editor confirms before save.
3. **Storage sits behind an interface**; the `Recipe` domain model is
   store-agnostic.

These keep the smart importers (§D) and images (§E) additive rather than
refactors. The backend reuses `_tools/` (parser + reportlab builders) as
library code via a `sys.path` shim — no reimplementation.

## Running it

```sh
pip install -r requirements-app.txt   # or requirements-dev.txt for lint+test
make serve                            # -> http://127.0.0.1:8000
```

`GET /health` returns `{"status": "ok"}`. Interactive API docs at `/docs`.
