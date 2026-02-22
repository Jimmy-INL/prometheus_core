UNAME := $(shell uname)

##@
##@ Help
##@

.PHONY: help
help: ##@ (Default) Print listing of key targets with their descriptions
	@printf "\nUsage: make <command>\n"
ifeq ($(UNAME), Linux)
	@grep -F -h "##@" $(MAKEFILE_LIST) | grep -F -v grep -F | sed -e 's/\\$$//' | awk 'BEGIN {FS = ":*[[:space:]]*##@[[:space:]]*"}; \
	{ \
			if($$2 == "") \
					pass; \
			else if($$0 ~ /^#/) \
					printf "\n\n%s\n", $$2; \
			else if($$1 == "") \
					printf "     %-20s%s\n", "", $$2; \
			else \
					printf "\n    \033[34m%-20s\033[0m %s", $$1, $$2; \
	}'
	@printf "\n\n"
else ifeq ($(UNAME), Darwin)
	@grep -F -h "##@" $(MAKEFILE_LIST) | grep -F -v grep -F | sed -e 's/\\$$//' | awk 'BEGIN {FS = ":*[[:space:]]*##@[[:space:]]*"}; \
	{ \
			if($$2 == "") \
					next; \
			else if($$0 ~ /^#/) \
					printf "\n\n%s\n", $$2; \
			else if($$1 == "") \
					printf "     %-20s%s\n", "", $$2; \
			else \
					printf "\n    \033[34m%-20s\033[0m %s", $$1, $$2; \
	}'
	@printf "\n\n"
else
	@printf "\make help not supported on $(UNAME)\n"
endif

##@
##@ Commands
##@

run: ##@ Start the backend API
	fastapi dev --port 8001 main.py

.PHONY: lint format typecheck check fix test

lint: ##@ Run ruff linter (report only)
	uv run ruff check .

format: ##@ Run ruff formatter (report only)
	uv run ruff format --check .

typecheck: ##@ Run mypy type checker
	uv run mypy main.py components/ utils/

test: ##@ Run unit tests
	uv run pytest

fix: ##@ Auto-fix ruff lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

check: ##@ Run all checks (lint + format + typecheck)
check: lint format typecheck
