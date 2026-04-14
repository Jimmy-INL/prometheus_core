UNAME := $(shell uname -s)

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
	@printf "\nmake help not supported on $(UNAME)\n"
endif

##@
##@ Checks
##@

.PHONY: lint format typecheck check fix test

lint: ##@ Run ruff linter (report only)
	uv run ruff check .

format: ##@ Run ruff formatter (report only)
	uv run ruff format --check .

typecheck: ##@ Run mypy type checker
	uv run mypy prometheus_api/

test: ##@ Run unit tests
	uv run pytest

fix: ##@ Auto-fix ruff lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

check: ##@ Run all checks (lint + format + typecheck)
check: lint format typecheck

.PHONY: test-install
test-install: ##@ Verify package installs and imports correctly in a clean venv
	@echo "Building package..."
	@uv build --quiet
	@TMPVENV=$$(mktemp -d) && \
	uv venv "$$TMPVENV" --quiet && \
	VIRTUAL_ENV="$$TMPVENV" uv pip install --quiet dist/prometheus_api-*.whl && \
	echo "Testing imports..." && \
	"$$TMPVENV/bin/python" -c "\
from prometheus_api import __version__; \
from prometheus_api.storage_client import StorageClient, AsyncStorageClient, ConnectionConfig; \
from prometheus_api.agent import PrometheusAgent; \
print(f'prometheus-api {__version__} OK')" && \
	rm -rf "$$TMPVENV" dist/ *.egg-info && \
	echo "Install check passed" || \
	(rm -rf "$$TMPVENV" dist/ *.egg-info; echo "Install check FAILED"; exit 1)

##@
##@ Versioning
##@

CURRENT_VERSION := $(shell grep -m1 '^version' pyproject.toml | sed 's/.*"\(.*\)"/\1/')
MAJOR := $(word 1,$(subst ., ,$(CURRENT_VERSION)))
MINOR := $(word 2,$(subst ., ,$(CURRENT_VERSION)))
PATCH := $(word 3,$(subst ., ,$(CURRENT_VERSION)))

.PHONY: version bump-patch bump-minor bump-major

version: ##@ Show current version
	@echo $(CURRENT_VERSION)

bump-patch: ##@ Bump patch version (0.2.0 → 0.2.1)
	$(eval NEW_VERSION := $(MAJOR).$(MINOR).$(shell echo $$(($(PATCH)+1))))
	@sed -i'' -e 's/^version = "$(CURRENT_VERSION)"/version = "$(NEW_VERSION)"/' pyproject.toml
	@echo "$(CURRENT_VERSION) → $(NEW_VERSION)"

bump-minor: ##@ Bump minor version (0.2.0 → 0.3.0)
	$(eval NEW_VERSION := $(MAJOR).$(shell echo $$(($(MINOR)+1))).0)
	@sed -i'' -e 's/^version = "$(CURRENT_VERSION)"/version = "$(NEW_VERSION)"/' pyproject.toml
	@echo "$(CURRENT_VERSION) → $(NEW_VERSION)"

bump-major: ##@ Bump major version (0.2.0 → 1.0.0)
	$(eval NEW_VERSION := $(shell echo $$(($(MAJOR)+1))).0.0)
	@sed -i'' -e 's/^version = "$(CURRENT_VERSION)"/version = "$(NEW_VERSION)"/' pyproject.toml
	@echo "$(CURRENT_VERSION) → $(NEW_VERSION)"

##@
##@ Container
##@

IMAGE_REPO ?=
IMAGE_TAG ?= $(shell git rev-parse --short HEAD)
PUSH_LATEST ?= false

build-image: ##@ Build container images for amd64 and arm64 (IMAGE_TAG=<tag>, default: git short hash)
	docker build --platform linux/amd64 -t "prometheus-api:$(IMAGE_TAG)-amd64" .
	docker build --platform linux/arm64 -t "prometheus-api:$(IMAGE_TAG)-arm64" .
	@echo "Built prometheus-api:$(IMAGE_TAG)-amd64 and prometheus-api:$(IMAGE_TAG)-arm64"

build-push: ##@ Build and push multi-arch image (IMAGE_REPO=<repo> [IMAGE_TAG=<tag>] [PUSH_LATEST=true|false])
ifndef IMAGE_REPO
	$(error IMAGE_REPO is required. Example: make build-push IMAGE_REPO=ghcr.io/my-org/prometheus-api)
endif
	docker build --platform linux/amd64 -t "$(IMAGE_REPO):$(IMAGE_TAG)-amd64" .
	docker build --platform linux/arm64 -t "$(IMAGE_REPO):$(IMAGE_TAG)-arm64" .
	docker push "$(IMAGE_REPO):$(IMAGE_TAG)-amd64"
	docker push "$(IMAGE_REPO):$(IMAGE_TAG)-arm64"
	docker manifest create "$(IMAGE_REPO):$(IMAGE_TAG)" \
		"$(IMAGE_REPO):$(IMAGE_TAG)-amd64" \
		"$(IMAGE_REPO):$(IMAGE_TAG)-arm64"
	docker manifest push "$(IMAGE_REPO):$(IMAGE_TAG)"
ifeq ($(PUSH_LATEST),true)
	docker manifest create "$(IMAGE_REPO):latest" \
		"$(IMAGE_REPO):$(IMAGE_TAG)-amd64" \
		"$(IMAGE_REPO):$(IMAGE_TAG)-arm64"
	docker manifest push "$(IMAGE_REPO):latest"
endif
	@echo "Done"
