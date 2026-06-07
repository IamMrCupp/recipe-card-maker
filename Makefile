# Recipes — build targets
#
# `make`          -> rebuild all PDFs + README
# `make pdfs`     -> rebuild all PDFs only
# `make readme`   -> regenerate README.md only
# `make clean`    -> remove all generated PDFs
# `make check`    -> sanity-parse every recipe and report
# `make lint`     -> ruff check + format-check on _tools/
# `make test`     -> pytest suite under tests/
# `make serve`    -> run the app backend (FastAPI) with auto-reload
# `make import-corpus` -> load the markdown corpus into the app's DB store
# `make export-corpus` -> write the DB store back to markdown + rebuild PDFs/README
# `make web-install` -> install the PWA frontend's npm deps (_web/)
# `make web-build`   -> build the PWA frontend (FastAPI serves _web/build)
# `make web-dev`     -> run the SvelteKit dev server (proxies /api to the backend)

PYTHON ?= python3
NPM    ?= npm
WEB    := _web
RUFF   ?= ruff
TOOLS  := _tools
HOST   ?= 127.0.0.1
PORT   ?= 8000

RECIPES := $(shell find . -name '*.md' -not -path './_*' -not -name 'README.md')

.PHONY: all pdfs readme clean check new lint test serve import-corpus export-corpus \
        web-install web-build web-dev

all: pdfs readme

pdfs:
	@echo "==> Building full-page PDFs"
	@$(PYTHON) $(TOOLS)/make_full_pdf.py
	@echo "==> Building 4x6 card PDFs"
	@$(PYTHON) $(TOOLS)/make_cards_pdf.py

readme:
	@echo "==> Regenerating README.md"
	@$(PYTHON) $(TOOLS)/update_readme.py

clean:
	@echo "==> Removing generated PDFs"
	@find . -name '*_full.pdf' -delete
	@find . -name '*_4x6.pdf' -delete

check:
	@echo "==> Parsing all recipes"
	@$(PYTHON) $(TOOLS)/recipe_parser.py .

lint:
	@echo "==> Ruff lint"
	@$(RUFF) check .
	@echo "==> Ruff format check"
	@$(RUFF) format --check .

test:
	@echo "==> Pytest"
	@$(PYTHON) -m pytest -q

serve:
	@echo "==> Starting app backend on http://$(HOST):$(PORT) (Ctrl-C to stop)"
	@$(PYTHON) -m uvicorn _app.main:app --reload --host $(HOST) --port $(PORT)

import-corpus:
	@echo "==> Importing markdown corpus into the DB store"
	@$(PYTHON) -m _app.corpus import

export-corpus:
	@echo "==> Exporting DB store to markdown + rebuilding PDFs/README"
	@$(PYTHON) -m _app.corpus export

web-install:
	@echo "==> Installing PWA frontend deps ($(WEB)/)"
	@cd $(WEB) && $(NPM) install

web-build:
	@echo "==> Building PWA frontend -> $(WEB)/build"
	@cd $(WEB) && $(NPM) run build

web-dev:
	@echo "==> Starting SvelteKit dev server (proxies /api to http://$(HOST):$(PORT))"
	@cd $(WEB) && $(NPM) run dev

# Scaffold a new recipe: `make new NAME=peach_galette CAT=pastries`
new:
	@if [ -z "$(NAME)" ] || [ -z "$(CAT)" ]; then \
		echo "Usage: make new NAME=<slug> CAT=<category>"; exit 1; \
	fi
	@if [ -e "$(CAT)/$(NAME).md" ]; then \
		echo "Error: $(CAT)/$(NAME).md already exists"; exit 1; \
	fi
	@mkdir -p $(CAT)
	@cp _templates/recipe_full.md $(CAT)/$(NAME).md
	@echo "Created $(CAT)/$(NAME).md"
