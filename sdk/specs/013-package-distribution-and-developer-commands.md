# 013 — Package distribution and developer commands

status: implemented
sources: pyproject.toml, Makefile, Dockerfile, README.md, DEVELOPMENT.md, INSTALL.md, prometheus_api/__init__.py
depends-on: 004, 008

## Purpose
Keep the package installable, versioned, testable, and container-buildable through the documented `uv` and Makefile workflow.

## Requirements
- REQ-013-01: The project metadata MUST publish the package as `prometheus-api`, require Python `>=3.12`, and use `README.md` as the package readme.
- REQ-013-02: `prometheus_api.__version__` MUST read the installed distribution version for `prometheus-api` and MUST fall back to `0.0.0+unknown` in an uninstalled source checkout.
- REQ-013-03: The setuptools package list MUST include the top-level package plus `llm_client`, `storage_client`, storage models/resources/async_resources/utils, and `agent`.
- REQ-013-04: Runtime dependencies MUST include the A2A server stack, `fsspec`, `httpx`, `litellm`, `pydantic`, `pyyaml`, `python-dateutil`, `python-dotenv`, `redis`, `starlette`, and `uvicorn[standard]`.
- REQ-013-05: Development dependencies MUST include pytest, pytest-asyncio, pytest-cov, mypy, ruff, and pre-commit.
- REQ-013-06: `make lint`, `make format`, and `make typecheck` MUST run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy prometheus_api/`.
- REQ-013-07: `make test` MUST alias the unit-test target, and `make test-unit` MUST run `uv run pytest -m "not integration"`.
- REQ-013-08: `make test-integration` MUST run only integration-marked tests, and `make test-all` MUST run all tests.
- REQ-013-09: `make fix` MUST run ruff auto-fix and formatting; `make check` MUST run lint, format, and typecheck.
- REQ-013-10: `make test-install` MUST build a wheel, install it in a clean temporary venv, smoke-test imports of `__version__`, storage clients/config, and `PrometheusAgent`, then clean build artifacts.
- REQ-013-11: Version targets MUST use `uv version --short` and `uv version --bump {patch,minor,major}`.
- REQ-013-12: Container build targets MUST support local amd64/arm64 image builds and multi-arch buildx push with configurable `IMAGE_REPO`, `IMAGE_TAG`, and optional latest tag.
- REQ-013-13: The Dockerfile MUST use a Python 3.12 `uv` base image, install runtime dependencies from `uv.lock` without dev dependencies, append any `certs/*.pem` files to the CA bundle, install the package without dependencies, and default to `python`.
- REQ-013-14: Pytest configuration MUST discover `tests/test_*.py`, enable `asyncio_mode=auto`, and define `unit`, `integration`, and `slow` markers.

## Behavior
- GIVEN the package is installed WHEN `from prometheus_api import __version__` is executed THEN the installed package version is returned. (id: BEH-013-01)
- GIVEN a source checkout not installed as a distribution WHEN `__version__` is imported THEN `0.0.0+unknown` is returned. (id: BEH-013-02)
- GIVEN `make test-install` succeeds THEN a clean venv can import the top-level, storage, and agent public APIs. (id: BEH-013-03)

## Interfaces
- `prometheus_api.__version__: str`
- `make help`
- `make lint`
- `make format`
- `make typecheck`
- `make check`
- `make fix`
- `make test`
- `make test-unit`
- `make test-integration`
- `make test-all`
- `make hooks`
- `make test-install`
- `make version`
- `make bump-patch`
- `make bump-minor`
- `make bump-major`
- `make build-image IMAGE_TAG=<tag>`
- `make build-push IMAGE_REPO=<repo> IMAGE_TAG=<tag> PUSH_LATEST=<true|false>`

## Constraints
- Developer and CI commands SHOULD run through `uv` so tool versions match `uv.lock`.
- Generated local files such as `.env`, `llm_config.yaml`, `.venv`, build outputs, and egg metadata must stay untracked.
- Container images target both `linux/amd64` and `linux/arm64`.

## Out of scope / Non-goals
- This package does not publish images or wheels by itself; external CI/release systems own publication.
- This spec does not require integration tests to pass without DeepLynx credentials.

## Open questions
- Makefile and Docker targets are not covered by automated unit tests beyond `make test-install` when run manually or in CI.
- Package version bump policy is not specified beyond the available `uv version` targets.
