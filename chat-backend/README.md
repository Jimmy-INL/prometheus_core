# chat-backend

Standalone FastAPI service that replaces Chainlit's server role for the Prometheus
Platform, exposing its own JSON/SSE contract. It has **zero Chainlit dependency** and
talks to the client-agent over A2A JSON-RPC (Bearer `AGENT_SECRET`), using Valkey/Redis
for session and conversation state.

This is a backend-only effort. The React frontend (`frontend-react/`) is rewired in a
separate follow-up; the old Chainlit app (`frontend/`) is left untouched.

## Layout

```
chat-backend/
  pyproject.toml
  app/
    main.py          # FastAPI() + lifespan + router mounts
    config.py        # pydantic-settings loader
    config.yml       # default configuration
    routers/
      health.py      # GET /healthz
  tests/
```

## Development

Requires Python 3.12+ and `uv` (the platform base image ships 3.12; the app also runs on 3.13).

```bash
uv sync
uv run uvicorn app.main:app --port 8600
curl localhost:8600/healthz          # {"status":"ok"}

uv run ruff check
uv run mypy app/
uv run pytest
```

## Configuration

`app/config.py` loads `app/config.yml` (override the path with `PROMETHEUS_CONFIG_PATH`).
Environment overrides:

| Env var | Setting |
|---------|---------|
| `CLIENT_AGENT_URL` | `agent_url` |
| `AGENT_SECRET` | `agent_secret` |
| `REDIS_URL` | `redis_url` |
| `PROMETHEUS_MAX_UPLOAD_BYTES` | `max_upload_bytes` (default 100 MB) |
| `CHAT_BACKEND_JWT_SECRET` / `CHAINLIT_AUTH_SECRET` | `jwt_secret` |
| `CHAT_BACKEND_COOKIE_NAME` | `cookie_name` |
| `CHAT_BACKEND_TOKEN_TTL_SECONDS` | `token_ttl_seconds` |

Default host port is **8600** (wired into compose/nginx in task 09).
