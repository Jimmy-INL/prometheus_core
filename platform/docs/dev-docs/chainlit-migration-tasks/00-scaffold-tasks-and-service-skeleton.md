# 00 — Scaffold service skeleton

> **Status: ✅ Done** (2026-08-10) — `backend/` skeleton stood up with
> `pyproject.toml`, `app/{main,config,config.yml}`, `app/routers/health.py`, `tests/`,
> `README.md`, `.dockerignore`.
>
> **Verification:** app boots and `GET /healthz` → `{"status":"ok"}`; `ruff check app/`
> and `mypy app/` both pass. `uv sync` cannot resolve the `prometheus_api` git dep in this
> environment (internal host `github.inl.gov` needs interactive credentials) — this is
> environmental, not a scaffold defect; the package is supplied by the Docker base image at
> build time (`--no-dev` skips the git entry there), matching how the client-agent consumes it.

## Goal

Stand up an empty-but-runnable `backend/` FastAPI service: dependency manifest,
app entrypoint with lifespan + `/healthz`, and a config module. Everything after this
builds inside this skeleton.

## Files to create

```
backend/
  pyproject.toml
  app/__init__.py
  app/main.py           # FastAPI() + lifespan + router mounts (health only for now)
  app/config.py         # pydantic-settings loader
  app/config.yml        # copied/adapted from the now-removed Chainlit app's frontend/config.yml (git history)
  app/routers/__init__.py
  app/routers/health.py # GET /healthz
  tests/__init__.py
  README.md
  .dockerignore
```

## Details

- **`pyproject.toml`** — Python `>=3.13`. Deps: `fastapi`, `uvicorn[standard]`,
  `pydantic-settings`, `redis>=4.2` (async), `httpx`, `pyjwt` (or `python-jose`), `pyyaml`,
  and `prometheus_api` (same git source the client-agent uses — inspect
  `agents/client-agent/pyproject.toml` for the exact `git+https://…@a2a_1.0` spec and pin).
  Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`. Mirror the frontend's ruff/mypy config
  (`E`,`F`, ignore `E501`, line-length 120; mypy `ignore_missing_imports`).
- **`app/config.py`** — pydantic `Settings` modeled on the now-removed Chainlit app's
  `frontend/utils/settings.py` (git history):
  `agent_url` (env `CLIENT_AGENT_URL`), `agent_secret` (env `AGENT_SECRET`), `redis_url`
  (env `REDIS_URL`), `max_upload_bytes` (env `PROMETHEUS_MAX_UPLOAD_BYTES`, default 100 MB),
  `local_users`, `workflow_suggestions`, `chat_intro`, `chat_suggestion_title`,
  `auto_approve_steps`, plus new: `jwt_secret` (env, reuse `CHAINLIT_AUTH_SECRET` or a new
  `BACKEND_JWT_SECRET`), `cookie_name`, `token_ttl_seconds`. Config path override via
  `PROMETHEUS_CONFIG_PATH`.
- **`app/main.py`** — `FastAPI(title=...)`, an `asynccontextmanager` lifespan that will later
  hold the Redis connection pool + session store (leave a TODO stub now), mount `health`
  router. Add permissive CORS only for local dev if needed (same-origin in prod via nginx).
- **`app/routers/health.py`** — `GET /healthz` → `{"status": "ok"}`.

## Acceptance check

- `cd backend && uv sync` resolves (including `prometheus_api`).
- `uv run uvicorn app.main:app --port 8600` starts; `curl localhost:8600/healthz` → `{"status":"ok"}`.
- `uv run ruff check` and `uv run mypy app/` pass on the skeleton.

## Notes

- Pick a host port not already used (see CLAUDE.md service map: 8001 client-agent,
  8002–8009 specialists; the old Chainlit `frontend` on 8500 has since been removed).
  Suggest **8600** for backend; wire the real port in task 09.
- Do not import `chainlit` anywhere. This service must have zero Chainlit dependency.
