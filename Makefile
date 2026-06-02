# Recipes — build targets
#
# `make`          -> rebuild all PDFs + README
# `make pdfs`     -> rebuild all PDFs only
# `make readme`   -> regenerate README.md only
# `make clean`    -> remove all generated PDFs
# `make check`    -> sanity-parse every recipe and report
# `make lint`     -> ruff check + format-check on _tools/

PYTHON ?= python3
RUFF   ?= ruff
TOOLS  := _tools

RECIPES := $(shell find . -name '*.md' -not -path './_*' -not -name 'README.md')

.PHONY: all pdfs readme clean check new lint

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
