# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`prometheus-api` is a Python 3.12+ package shipping two cooperating components against a DeepLynx storage backend:

1. **`prometheus_api.storage_client`** — Pydantic-typed sync (`StorageClient`) and async (`AsyncStorageClient`) HTTP clients for items, files (incl. chunked uploads), relationships, search, tags, timeseries. Also registers a `deeplynx://` fsspec filesystem (`DeepLynxFileSystem`) via the `fsspec.specs` entry point.
2. **`prometheus_api.agent`** — `PrometheusAgent` base class for A2A-protocol agents (built on `a2a-sdk` + Starlette/uvicorn). Subclasses override `async _execute(params, context, event_queue)` and the base handles agent-card loading, bearer-token auth, registry registration, status/artifact emission, and per-`contextId` state persistence.

`prometheus_api.contract` (package top level, importable with only pydantic — no agent runtime) holds the canonical frontend ↔ client-agent wire contract (`ConversationRequest`, `ConversationResponse`, `ConversationStatus`) — the JSON payload exchanged in A2A text parts. The Prometheus platform's frontend and client-agent must import these models rather than redefining them; change them here and the change propagates to both sides. They are also re-exported from `prometheus_api.agent`.

Two more shared, dependency-light top-level modules (do not copy their logic into consumers):
- `prometheus_api.a2a_stream` — client-side consumption of A2A `message/stream` responses (SSE/NDJSON parsing, heartbeat skipping, status/background callbacks, artifact merge). Used by the platform frontend and client-agent.
- `prometheus_api.redis_utils` — `create_redis_client()`, the single Redis connection recipe (`REDIS_URL`/`REDIS_PASSWORD`, `decode_responses=True`, fail-fast ping, logged `None` on failure). The agent stores (`ArtifactRegistry`, `ContextStateStore`, `RedisTaskStore`) build their connections through it.

Artifact-to-file resolution (cache layout, allowed local roots, fsspec downloads, inline materialization) lives in `prometheus_api.agent.artifact_resolver.ArtifactResolver`; `PrometheusAgent.get_artifact_file_path` is a thin delegate bound to the agent's registry.

The agent component depends on the storage client (used internally for `ContextStateStore` and artifact persistence). The A2A server stack (`a2a-sdk[http-server]`, `starlette`, `uvicorn`) is part of the base `dependencies` — there is no `[agent]` extra.

## Common Commands

Use `uv run` (the project is uv-managed; see `uv.lock`). The Makefile wraps the common targets:

```bash
make lint             # ruff check .
make format           # ruff format --check .
make typecheck        # mypy prometheus_api/
make test             # alias for `test-unit` (skips integration)
make test-unit        # pytest -m "not integration"
make test-integration # pytest -m integration (requires .env)
make test-all         # pytest (every marker, including integration)
make fix              # ruff check --fix . && ruff format .
make check            # lint + format + typecheck
make hooks            # install pre-commit + pre-push hooks
make test-install     # build wheel via `uv build`, install in clean venv, smoke-test imports
```

`make test` is an alias for `make test-unit` — it does **not** run integration tests by default. Use `make test-all` to include them.

### Targeted test runs

```bash
uv run pytest -m "not integration"                          # unit only (no .env required)
uv run pytest -m integration                                # integration (requires .env w/ DeepLynx creds)
uv run pytest tests/test_agent.py::TestPrometheusAgentExecutor::test_execute_calls_enqueue_event
uv run pytest --cov=prometheus_api --cov-report=html
```

`pyproject.toml` sets `asyncio_mode = "auto"`, so async tests do **not** need `@pytest.mark.asyncio`. Tests in `test_integration.py` are auto-marked `integration` by `tests/conftest.py`.

### Versioning & container builds

```bash
make version                                         # prints version from pyproject.toml
make bump-patch | bump-minor | bump-major            # rewrites pyproject.toml
make build-image IMAGE_TAG=<tag>                     # local amd64+arm64 builds
make build-push IMAGE_REPO=<repo> [PUSH_LATEST=true] # multi-arch buildx push (default repo: containers.github.inl.gov/...)
```

Default `IMAGE_TAG` is `git rev-parse --short HEAD`.

## Architecture Notes

### StorageClient layout
`StorageClient` (sync) and `AsyncStorageClient` (async) are thin lifecycle managers; all real work lives in **resource handlers** lazy-loaded as properties (`client.items`, `.files`, `.relationships`, `.search`, `.tags`, `.timeseries`). The sync and async resource trees are kept as parallel modules — `storage_client/resources/` and `storage_client/async_resources/` — and must be edited together when adding/changing endpoints. Models (`storage_client/models/`) are shared between both.

`ConnectionConfig` is a frozen Pydantic model that requires either (`api_key` + `api_secret`) **or** `jwt_token`, never both. It validates at construction. Use `ConnectionConfig.from_env()` to load from `DEEPLYNX_*` env vars (see `.env.example`). The default `base_url` is `https://deeplynx.inl.gov/api/v1`.

`DeepLynxFileSystem` (fsspec) maps `deeplynx://` URIs to DeepLynx file records, storing object keys in record metadata rather than building a separate index. It's wired up automatically via the `[project.entry-points."fsspec.specs"]` declaration in `pyproject.toml`.

### PrometheusAgent contract
Subclasses override `async _execute(self, params, context: RequestContext, event_queue: EventQueue) -> dict`. The returned dict becomes the final task status — the base class emits the terminal `TaskStatusUpdateEvent` automatically. Inside `_execute`, use the helpers rather than constructing A2A events manually:

- `send_status_update(...)` — transient progress
- `send_artifact_reference(...)` — URI-backed file artifact (e.g. `deeplynx://...`)
- `send_json_artifact(..., catalog_artifact=True)` — reusable inline JSON artifact
- `send_conversation_message(...)` — durable chat-visible message
- `send_input_required(missing_inputs=[MissingInput(...)])` — INPUT_REQUIRED with canonical payload
- `load_context_state(...)` / `save_context_state(...)` — per-`contextId` resumable state via `ContextStateStore`

The agent module also re-exports common A2A types (`RequestContext`, `EventQueue`, `TaskState`, `TaskStatus`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `Artifact`, `TextPart`) from `prometheus_api.agent`, so subclasses normally don't need to import directly from `a2a.*`.

Streaming (`message/stream`) is opt-in: set `"capabilities": {"streaming": true}` in the agent's `agent_card.json`. Bearer-token auth via `BearerTokenMiddleware` is enforced when `AGENT_SECRET` is set; setting `AGENT_SECRET_REQUIRED=false` is a development-only escape hatch.

Artifact metadata produced by helpers always carries `conversation_id`, `producer_agent_id` (normalized: lowercased, spaces → hyphens), and `created_at` (UTC ISO). When adding new helper paths that emit artifacts, route through `_build_artifact_metadata` to preserve this envelope.

### Tests
- `test_*.py` files at the top level of `tests/` are unit tests.
- `test_integration.py` requires a `.env` with valid `DEEPLYNX_KEY`/`SECRET`/`ORG_ID`/`PROJECT_ID` and optionally `DEEPLYNX_DATA_SOURCE_ID` (without it, code that creates records will hit "DataSource with id 0 not found").
- `make test-install` builds a wheel, installs it into a clean venv, and smoke-tests the imports. Use this rather than ad-hoc shell scripts.

## Conventions

- **Python ≥ 3.12** is hard-required (`requires-python` and `target-version` in ruff/mypy).
- Line length is **100** (ruff). `examples/` is excluded from ruff and mypy.
- Use the Makefile targets rather than running `pytest`/`ruff`/`mypy` directly, so dev tooling stays in sync with `uv.lock`.
- Container images target both `linux/amd64` and `linux/arm64`; the Dockerfile installs the base package and concatenates any `certs/*.pem` into the system CA bundle.
- When you make a change, ensure that this file gets updated to reflect those changes. We do not want this file getting out of date so it is important that when you make changes, they are accurately documented in this file.
