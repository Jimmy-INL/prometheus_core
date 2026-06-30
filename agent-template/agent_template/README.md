# TEMPLATE_NAME Agent

TEMPLATE_DESCRIPTION

A Prometheus specialist agent that speaks the Agent-to-Agent (A2A) protocol. The
platform's orchestrator discovers it, routes user requests to it, and renders its
responses in the Chainlit UI.

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Your code. Subclass of `PrometheusAgent`; implements `_execute`. |
| `agent_card.json` | Declares the agent's name, description, and skills. The orchestrator reads this to decide when to route to you. |
| `pyproject.toml` | Extra Python dependencies your code imports directly. |
| `Dockerfile` | Builds the image from the pinned `prometheus_api` base image. |
| `docker-compose.yml` | Runs the image alongside (or inside) the platform. |
| `Makefile` | Convenience wrapper around `docker compose` (`make up`, `make up-fg`, `make down`, `make logs`). |
| `.env.example` | Template for `.env` — copy and fill in real values. |

`prometheus_api`, `a2a`, `starlette`, and `uvicorn` are already installed in the
base image — do **not** add them to `pyproject.toml`.

## Run locally (fast iteration)

```bash
cp .env.example .env          # then fill in real values

uv sync                       # creates .venv with your deps + dev tools (pytest, ruff)
source .venv/bin/activate

# Install prometheus_api pinned to the platform's base image hash
# (PROMETHEUS_API_BASE_IMAGE_HASH in your .env) so local dev matches the
# container. Re-run this when the platform bumps the hash.
uv pip install "git+https://github.inl.gov/genesis/prometheus_api.git@$(grep -E '^PROMETHEUS_API_BASE_IMAGE_HASH=' .env | cut -d= -f2)"

AGENT_SECRET_REQUIRED=false python agent.py
```

The agent starts on `http://localhost:8000`. Test it:

```bash
curl -s -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AGENT_SECRET" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [{"kind": "text", "text": "{\"input_data\": \"hello\"}"}],
        "metadata": {"skillId": "TEMPLATE_SKILL_ID"}
      }
    }
  }' | python -m json.tool
```

(`skillId` lives in `message.metadata` — that is where the base class reads it.)

Without Redis, per-conversation state and the artifact registry fall back to an
in-memory dict — fine for local development.

## Run the tests

```bash
uv run pytest                 # tests/ — extend as you implement _execute
uv run ruff check .           # lint
```

## Run with Docker

Optionally set `PROMETHEUS_API_BASE_IMAGE_HASH` in `.env` (find the current value in
`prometheus_platform/Makefile`), or let it default to `latest`, then:

```bash
make up-fg       # build + start in the foreground (Ctrl-C to stop)
make up          # build + start detached
make logs        # tail logs (add SERVICE=<name> for one service)
make down        # stop and remove
```

These wrap `docker compose` and, on Linux, layer in `docker-compose.linux.yml`
if you create one. The raw commands (`docker compose up --build`, etc.) still
work if you prefer them.

Pick the right network block in `docker-compose.yml`:

- **Option A — external repo:** your agent joins the platform's network. Start
  the platform first (`make up`), then `docker compose up --build` here.
- **Option B — in-tree:** copy this directory into
  `prometheus_platform/agents/<name>/`, switch to the in-tree network block, then
  run `make generate && make up` from the platform.

## Customizing

1. **`agent_card.json`** — set `name`, `description` (a one-sentence capability
   statement the orchestrator reads), and the skill's `inputSchema`,
   `output_format`, and `usage_notes`.
2. **`agent.py`** — read your inputs from `params`, do the work, return a plain
   `dict`. Use `self.send_status_update(...)` for progress messages.
3. **`pyproject.toml`** — add any packages your code imports.

See **TUTORIAL.md** in the template repository for a full walkthrough, including
emitting artifacts, asking the user for missing inputs (`INPUT_REQUIRED`),
multiple skills, and DeepLynx file storage.

## Key environment variables

| Variable | Purpose |
|----------|---------|
| `AGENT_PORT` | Port the agent listens on (default `8000`). |
| `EXTERNAL_AGENT_URL` | Optional full URL the registry uses to reach this agent. Defaults to `http://{container hostname}:{AGENT_PORT}` (the Docker service name), which is right for in-network deployments; set it only when port-mapped or on another host. |
| `AGENT_SECRET` | Shared bearer token for A2A auth. Must match the platform's. |
| `AGENT_SECRET_REQUIRED` | Set `false` to disable auth — local development only. |
| `REGISTRY_URL` | LiteLLM proxy URL where the agent registers on startup. |
| `LITELLM_MASTER_KEY` | LiteLLM gateway auth. |
| `REDIS_URL` / `REDIS_PASSWORD` | Conversation state and artifact registry. |
| `PROMETHEUS_API_BASE_IMAGE_HASH` | Base image tag the Dockerfile builds from. |

See `.env.example` for the full list (including optional DeepLynx and proxy settings).
