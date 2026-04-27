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

.PHONY: lint format typecheck check fix test test-unit test-integration test-all hooks

lint: ##@ Run ruff linter (report only)
	uv run ruff check .

format: ##@ Run ruff formatter (report only)
	uv run ruff format --check .

typecheck: ##@ Run mypy type checker
	uv run mypy prometheus_api/

test: ##@ Run unit tests (default test target)
test: test-unit

test-unit: ##@ Run unit tests without integration tests
	uv run pytest -m "not integration"

test-integration: ##@ Run integration tests (requires .env with DeepLynx credentials)
	uv run pytest -m integration

test-all: ##@ Run all tests, including integration tests
	uv run pytest

fix: ##@ Auto-fix ruff lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

check: ##@ Run all checks (lint + format + typecheck)
check: lint format typecheck

hooks: ##@ Install pre-commit and pre-push hooks
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

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

.PHONY: version bump-patch bump-minor bump-major

version: ##@ Show current version
	@uv version --short

bump-patch: ##@ Bump patch version (0.2.0 → 0.2.1)
	@uv version --bump patch

bump-minor: ##@ Bump minor version (0.2.0 → 0.3.0)
	@uv version --bump minor

bump-major: ##@ Bump major version (0.2.0 → 1.0.0)
	@uv version --bump major

##@
##@ Container
##@

IMAGE_REPO ?= mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312
IMAGE_TAG ?= $(shell git rev-parse --short HEAD)
BUILD_PUSH_TAGS := -t "$(IMAGE_REPO):$(IMAGE_TAG)"

build-image: ##@ Build container images for amd64 and arm64 (IMAGE_TAG=<tag>, default: git short hash)
	docker build --platform linux/amd64 -t "prometheus-api:$(IMAGE_TAG)-amd64" .
	docker build --platform linux/arm64 -t "prometheus-api:$(IMAGE_TAG)-arm64" .
	@echo "Built prometheus-api:$(IMAGE_TAG)-amd64 and prometheus-api:$(IMAGE_TAG)-arm64"

build-push: ##@ Build and push multi-arch image (IMAGE_REPO=<repo> [IMAGE_TAG=<tag>])
ifndef IMAGE_REPO
	$(error IMAGE_REPO is required. Example: make build-push IMAGE_REPO=ghcr.io/my-org/prometheus-api)
endif
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		--push \
		$(BUILD_PUSH_TAGS) \
		.
	@echo "Done"
