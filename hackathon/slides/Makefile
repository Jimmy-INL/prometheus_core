# Slides are written in slides/*.md; the NN-*.html decks are generated.
UV_BUILD = uv run -q --with markdown-it-py --with mdit-py-plugins --with pygments --with pyyaml
UV_PW    = uv run -q --with playwright

.PHONY: build check pdf all
all: build check

build: ## slides/*.md -> NN-*.html
	$(UV_BUILD) python tools/build.py $(DECKS)

check: ## layout check (overlaps, overflow) for every deck
	$(UV_PW) python tools/check_layout.py $(addsuffix .html,$(basename $(notdir $(DECKS))))

pdf: ## one PDF per deck in pdf/
	$(UV_PW) python tools/export_pdf.py
