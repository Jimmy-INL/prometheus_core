# Repository Guidelines

## Project Structure & Module Organization

`prometheus_api/` contains the package source. `storage_client/` implements the DeepLynx sync and async clients, resource handlers, shared Pydantic models, filesystem integration, and utilities. `agent/` contains A2A agent base classes, middleware, artifact helpers, and context state handling. `llm_client/` contains provider-agnostic LiteLLM sync and async chat/embedding clients, config parsing, input normalization, response models, and secret redaction. Keep sync and async storage resources aligned when changing endpoint behavior.

`tests/` contains pytest tests named `test_*.py`; integration coverage is concentrated in `tests/test_integration.py`. `examples/` has runnable usage examples and is excluded from ruff and mypy checks. `docs/` contains longer guides; update it when public behavior changes. `docs/agent/LLM_CLIENT_MIGRATION.md` guides people and AI coding assistants through replacing vendor-specific LLM utilities with `llm_client`. `llm_config.example.yaml` is the tracked local-development fallback template, including optional LiteLLM `api_base` examples; developer-specific copies such as `llm_config.yaml` must stay untracked.

## Build, Test, and Development Commands

Use the Makefile so tools run through the locked `uv` environment:

```bash
make test          # run unit tests with project defaults
make lint          # run ruff check .
make format        # verify ruff formatting
make typecheck     # run mypy on prometheus_api/
make fix           # apply ruff fixes and formatting
make check         # lint + format + typecheck
make test-install  # build wheel, install in a clean venv, smoke-test imports
make build-image IMAGE_TAG=dev
```

For targeted tests, use `uv run pytest tests/test_agent.py::TestPrometheusAgentExecutor`.

## Coding Style & Naming Conventions

This project targets Python 3.12+. Ruff uses a 100-character line length and excludes `examples/`. Prefer typed Pydantic models for API payloads, explicit resource classes for endpoints, and clear async/sync parity between `storage_client/resources/` and `storage_client/async_resources/`. Keep `llm_client` sync and async behavior aligned when changing aliases, fallback behavior, logging, or response objects. Use `snake_case` for modules, functions, variables, and test functions; use `PascalCase` for classes.

## Testing Guidelines

Pytest configuration lives in `pyproject.toml`. Test files, classes, and functions should follow `test_*.py`, `Test*`, and `test_*`. Async tests are supported through `asyncio_mode = "auto"`. Run unit tests with `uv run pytest -m "not integration"`. Integration tests require a configured `.env` based on `.env.example` with valid `DEEPLYNX_*` credentials.

## Commit & Pull Request Guidelines

Recent commits use short, direct summaries such as `fix tag ids` or `Cleaned up docs`. Keep commit subjects concise and focused on one change. For pull requests, include a brief description, test commands run, linked issue or context, and note any credential, environment, Docker image, or DeepLynx behavior changes. Add screenshots only for documentation or UI-facing changes.

## Security & Configuration Tips

Do not commit `.env`, secrets, API keys, generated certificates, or local caches. Use `.env.example` for documenting required variables. Treat integration credentials, DeepLynx IDs, `REGISTRY_URL`, and LLM provider keys as environment-specific configuration, not hard-coded defaults. LLM debug logging must keep prompt and embedding content hidden unless `LLM_DEBUG_LOG_MESSAGES=true`, and structured A2A `llm_api_key` values must be redacted from logs.

## Additional Instructions

When you make a change, ensure that this file gets updated to reflect those changes. We do not want this file getting out of date so it is important that when you make changes, they are accurately documented in this file.
