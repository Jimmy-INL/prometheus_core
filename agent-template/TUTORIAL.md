# Writing a Prometheus Agent

This tutorial walks you through building a specialist agent for the Prometheus multi-agent platform from scratch. You will create a stand-alone Python project, containerize it with Docker, and connect it to a running Prometheus platform instance.

**Assumed knowledge:** Basic Python (classes, `async`/`await`). No Docker experience required — Docker concepts are introduced as needed.

---

## What you are building

A Prometheus agent is a small HTTP service that speaks the [A2A protocol](https://google.github.io/A2A/). The platform's orchestrator discovers it, routes user requests to it, and displays its responses in the Chainlit chat UI.

```
User → Chainlit UI → Orchestrator (client-agent)
                          │
                          │  A2A JSON-RPC over HTTP
                          ▼
                     Your Agent  ←─── LiteLLM (LLM calls)
                          │
                          └── Redis (state, artifact catalog)
```

Every agent is built from **five files**:

| File | Purpose |
|------|---------|
| `agent_card.json` | Declares the agent's name, description, and skills. The orchestrator reads this at startup. |
| `agent.py` | Your Python code. Subclass `PrometheusAgent`, implement `_execute`. |
| `pyproject.toml` | Python packaging metadata and your extra dependencies. |
| `Dockerfile` | Turns your code into a Docker image. |
| `docker-compose.yml` | Runs the image as part of (or alongside) the Prometheus platform. |

---

## Prerequisites

- **Python 3.12+** — `python3 --version`
- **uv** — the package manager used across the platform. Install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker Desktop** (or Podman) — only needed for Steps 6–9
- **Git** — for cloning and version control
- Access to the `prometheus_api` base image registry (`containers.github.inl.gov/genesis/prometheus_api`) — or the platform's `.env` file, which has the `PROMETHEUS_API_BASE_IMAGE_HASH` value

---

## Step 1 — Create your project

Clone the template repository and run the interactive scaffolder. It copies the
canonical template (in `agent_template/`) into a new directory, replacing the
`TEMPLATE_*` placeholders with your agent's name, slug, class, and primary skill:

```bash
git clone git@github.inl.gov:genesis/prometheus_agent_template.git
cd prometheus_agent_template
python setup_agent.py
```

Answer the prompts (agent name, description, slug, class name, skill). When it
finishes, your new project lives in the output directory you chose:

```
my-agent/
├── agent.py
├── agent_card.json
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

> **Prefer to do it by hand?** Copy `agent_template/` into a new directory and
> replace the `TEMPLATE_*` placeholders (`TEMPLATE_NAME`, `TEMPLATE_DESCRIPTION`,
> `TEMPLATE_CLASS`, `TEMPLATE_SLUG`, `TEMPLATE_SKILL_ID`, `TEMPLATE_SKILL_NAME`,
> `TEMPLATE_SKILL_DESCRIPTION`) yourself. The walkthrough below uses concrete
> example values (`My Agent`, `my_skill`, `input_text`) to show what to put.

Move into your new agent directory and create your `.env` (it holds your secrets
and is never committed):

```bash
cd my-agent
cp .env.example .env
```

Then set up a local Python environment for development:

```bash
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

---

## Step 2 — The agent card (`agent_card.json`)

The agent card is a JSON file that tells the orchestrator everything it needs to know to route requests to your agent. Open `agent_card.json`:

```json
{
  "name": "My Agent",
  "description": "One sentence description used by the orchestrator to route requests.",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [ ... ]
}
```

### Top-level fields

| Field | What to put here |
|-------|-----------------|
| `name` | Human-readable name shown in the UI. |
| `description` | **One sentence** used by the LLM orchestrator when deciding which agent to call. Write it as a capability statement: *"Analyzes corrosion rates for stainless steel alloys given temperature and pH."* |
| `url` | Leave as `"http://localhost:8000"`. The base class overwrites this at runtime with the container's actual hostname. |
| `version` | Semantic version of your agent. Increment when the skill interface changes. |
| `capabilities.streaming` | Set `true` only if your agent emits streaming partial responses (rare; not needed for most agents). |

### Skills

Each skill is one thing your agent can do. Most agents have one skill; some have a few. The orchestrator passes the `skillId` to your `_execute` call as `params["skill_id"]` so you can dispatch to the right handler.

```json
{
  "id": "my_skill",
  "name": "My Skill",
  "description": "What this skill does. One or two sentences.",
  "usage_notes": "When the user asks about X. Use this instead of Y when Z.",
  "requires_approval": false,
  "expected_duration_seconds": 10,
  "output_format": "JSON with keys: status, result",
  "inputSchema": { ... }
}
```

| Field | Notes |
|-------|-------|
| `id` | Snake-case identifier used in code, e.g. `"analyze_corrosion"`. |
| `description` | Read by the LLM to decide when to invoke this skill. Be specific. |
| `usage_notes` | Clarifies edge cases: when to prefer this skill over a similar one, what context is needed. |
| `requires_approval` | If `true`, the UI pauses and asks the user to confirm before the skill runs. |
| `expected_duration_seconds` | Informational; used by the UI to set timeout expectations. |
| `output_format` | Prose description of the return value shape. Used by the orchestrator when constructing multi-step plans. |

### `inputSchema`

This is a [JSON Schema](https://json-schema.org/) object describing the parameters your skill accepts. The orchestrator uses it to know what it needs to collect before calling your agent, and to validate inputs.

```json
"inputSchema": {
  "type": "object",
  "properties": {
    "material_id": {
      "type": "string",
      "description": "Material identifier, e.g. 'SS316L'."
    },
    "temperature_c": {
      "type": "number",
      "description": "Operating temperature in °C."
    },
    "coolant": {
      "type": "string",
      "description": "Coolant type.",
      "enum": ["water", "helium", "sodium"]
    }
  },
  "required": ["material_id"]
}
```

Tips:
- Mark only truly required fields as `required`. Optional fields let the orchestrator call your agent with partial information.
- Use `"description"` on every property — these descriptions are read by the LLM when constructing calls.
- Use `"enum"` for fixed-value fields to prevent the orchestrator from guessing.
- Add `"x_input_source": "runtime"` to a property whose value will be provided by a previous agent's output rather than by the user directly.

**Fill in the specifics.** If you used `setup_agent.py`, the name, skill id, and skill name are already set — you still need to refine the `description`, `usage_notes`, `output_format`, and the `inputSchema` properties for your agent. If you copied the template by hand, replace the `TEMPLATE_*` placeholders too.

---

## Step 3 — The Python agent (`agent.py`)

Open `agent.py`. The structure is:

```python
from prometheus_api.agent import PrometheusAgent
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue) -> dict:
        ...
        return {"status": "success", "result": ...}

if __name__ == "__main__":
    MyAgent(agent_name="My Agent").run()
```

That is all the code you need to write. The base class (`PrometheusAgent`) handles the HTTP server, authentication, agent-card serving, and registry registration.

### The `_execute` contract

`_execute` is called once per incoming request. It receives:

| Argument | Type | What it contains |
|----------|------|-----------------|
| `params` | `dict` | Parameters from the caller's JSON payload, plus `skill_id` from message metadata. |
| `context` | `RequestContext` | The A2A request context. Use `context.context_id` as a stable key for per-conversation state. |
| `event_queue` | `EventQueue` | Pass to helper methods to emit progress updates and artifacts. |

It must return a `dict`. The base class automatically wraps the returned dict as the final `completed` task status. The orchestrator receives this dict as the agent's result.

### Reading parameters

```python
async def _execute(self, params, context, event_queue):
    material_id = params.get("material_id")
    temperature  = params.get("temperature_c", 25.0)   # with default
    skill_id     = params.get("skill_id")               # which skill was called

    if not material_id:
        return {"status": "error", "error": "material_id is required"}
```

### Sending status updates

The base class sends the initial `"working"` status automatically. Call `send_status_update` for intermediate messages that appear in the UI while your agent is running:

```python
await self.send_status_update(
    context=context,
    event_queue=event_queue,
    message="Fetching material properties…",
)
# ... do some work ...
await self.send_status_update(
    context=context,
    event_queue=event_queue,
    message="Running analysis…",
)
```

### Returning a result

Just return a plain dict. Keep the keys consistent with what you described in `output_format` in the agent card:

```python
return {
    "status": "success",
    "material_id": material_id,
    "result": { ... },
    "agent": self.agent_name,
}
```

---

## Step 4 — Adding your logic

This is where you replace the `TODO` placeholder with real work.

### Example A: Calling Claude

This mirrors what the synthesis-agent does. Install `anthropic` first (see Step 5).

```python
import os
from anthropic import Anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-6")

class SummarizerAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        text = params.get("text")
        if not text:
            return {"status": "error", "error": "text is required"}

        await self.send_status_update(context, event_queue, message="Summarizing…")

        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=512,
            messages=[{"role": "user", "content": f"Summarize this in 2-3 sentences:\n\n{text}"}],
        )

        return {
            "status": "success",
            "summary": response.content[0].text,
        }
```

Alternatively, use the built-in `LLMClient` which routes through LiteLLM (same as the rest of the platform):

```python
class SummarizerAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        text = params.get("text")
        await self.send_status_update(context, event_queue, message="Summarizing…")

        async with self.llm_client(context) as llm:
            response = await llm.medium(f"Summarize this in 2-3 sentences:\n\n{text}")

        return {"status": "success", "summary": response.text}
```

### Example B: Calling an external HTTP API

```python
import httpx

class DataFetcherAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        record_id = params.get("record_id")
        await self.send_status_update(context, event_queue, message="Fetching record…")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.example.com/records/{record_id}",
                headers={"Authorization": f"Bearer {os.getenv('MY_API_KEY')}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return {"status": "success", "record": data}
```

### Example C: CPU-bound / synchronous library

If your computation uses a blocking library (NumPy, SciPy, a legacy analysis tool), run it in a thread pool so it does not block the async event loop:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_POOL = ThreadPoolExecutor(max_workers=4)

class SimulationAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        await self.send_status_update(context, event_queue, message="Running simulation…")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_POOL, self._run_simulation, params)
        return {"status": "success", "result": result}

    def _run_simulation(self, params):
        # blocking computation here — regular synchronous Python
        import numpy as np
        data = np.array(params.get("values", []))
        return {"mean": float(data.mean()), "std": float(data.std())}
```

### Reading environment variables

Never hard-code secrets or URLs. Read them from environment variables using `os.getenv`:

```python
API_KEY  = os.getenv("MY_API_KEY")        # returns None if not set
BASE_URL = os.getenv("BASE_URL", "https://api.example.com")  # with default
```

Values come from your `.env` file locally and from the `environment:` block in `docker-compose.yml` when containerized. You add the variables in both places (see Step 7).

---

## Step 5 — Python packaging (`pyproject.toml`)

`pyproject.toml` tells uv (and pip) what packages your agent needs. Open the file:

```toml
[project]
name = "my-agent"
version = "0.1.0"
description = "One-sentence description"
requires-python = ">=3.12"
dependencies = [
    # your packages here
]
```

**Add only packages that your agent code imports directly.** The base image already has `prometheus_api`, `a2a`, `starlette`, and `uvicorn` installed — listing them here would install a second copy and could cause version conflicts.

```toml
dependencies = [
    "anthropic>=0.18.0",   # if you call Claude directly
    "httpx>=0.26.0",       # if you call external HTTP APIs
    "numpy>=1.26.0",       # if you use NumPy
]
```

After editing `pyproject.toml`, sync your local environment:

```bash
uv pip install -r <(uv export --no-hashes)
# or simply:
uv pip install anthropic httpx   # for quick iteration
```

---

## Step 6 — Docker primer and Dockerfile

### What Docker is

Docker packages your code and all its dependencies into a **container image** — a portable, self-contained unit that runs identically on any machine. You build an image once and run it anywhere.

- An **image** is the blueprint (built from a `Dockerfile`).
- A **container** is a running instance of an image.
- A **base image** is a pre-built image your image extends. The platform publishes one (`prometheus_api`) that already has Python, prometheus_api, and all agent infrastructure installed.

### Your Dockerfile

```dockerfile
ARG PROMETHEUS_API_BASE_IMAGE_HASH
FROM containers.github.inl.gov/genesis/prometheus_api:${PROMETHEUS_API_BASE_IMAGE_HASH}
```
Starts from the pre-built base image, pinned to a specific hash for reproducibility. The hash is passed in as a build argument — you never change this line directly; you change the value in `.env` or the platform's `Makefile`.

```dockerfile
WORKDIR /app
```
Sets the working directory inside the container. All subsequent paths are relative to `/app`.

```dockerfile
ENV UV_PROJECT_ENVIRONMENT="/usr/local" \
    UV_LINK_MODE=copy
```
Configures uv to install packages into the system Python (where `prometheus_api` is already installed) rather than a separate virtual environment.

```dockerfile
COPY pyproject.toml /app/
RUN --mount=type=cache,...  uv sync --no-dev --no-install-project --inexact
```
Copies the dependency manifest and installs your packages. This layer is cached by Docker: if `pyproject.toml` hasn't changed since the last build, Docker skips the `RUN` line entirely — making subsequent rebuilds very fast.

```dockerfile
COPY agent.py /app/agent.py
COPY agent_card.json /app/agent_card.json
```
Copies your source files last. This ordering means code changes (the most frequent change) only invalidate the final layer, not the dependency installation layer.

```dockerfile
EXPOSE 8000
CMD ["python", "agent.py"]
```
Documents that the container listens on port 8000 and sets the default startup command.

### Building the image manually

You don't normally need to build manually — `docker compose up` does it. But to check that your Dockerfile is correct:

```bash
# Get the current hash from prometheus_platform/Makefile or your .env
export PROMETHEUS_API_BASE_IMAGE_HASH=dd30466

docker build \
  --build-arg PROMETHEUS_API_BASE_IMAGE_HASH=$PROMETHEUS_API_BASE_IMAGE_HASH \
  -t my-agent:dev .
```

---

## Step 7 — Platform wiring (`docker-compose.yml`)

### What Docker Compose is

Docker Compose is a tool that starts multiple containers together from a single YAML file. It handles naming, networking, and environment variables so you don't have to pass long `docker run` commands by hand.

### Key sections in your `docker-compose.yml`

```yaml
services:
  my-agent:
    build:
      context: .
      args:
        PROMETHEUS_API_BASE_IMAGE_HASH: ${PROMETHEUS_API_BASE_IMAGE_HASH}
```
Tells Compose to build the image from the current directory using the `Dockerfile` here. The `${...}` syntax reads values from your `.env` file or the shell environment.

```yaml
    container_name: my-agent
    networks:
      - agent-network
```
Gives the container a stable hostname (`my-agent`) on the shared network. Other containers can reach your agent at `http://my-agent:8000`.

```yaml
    environment:
      AGENT_PORT: 8000
      AGENT_SECRET: ${AGENT_SECRET}
      REGISTRY_URL: ${REGISTRY_URL:-}
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
      REDIS_URL: ${REDIS_URL:-redis://redis:6379}
      REDIS_PASSWORD: ${REDIS_PASSWORD}
```
Passes secrets and configuration into the container at runtime. Values come from `.env` (the `${VAR}` references). The `:-` syntax provides a default if the variable is not set.

**Add your own agent-specific variables here and in `.env`:**

```yaml
      MY_API_KEY: ${MY_API_KEY:-""}
      MY_BASE_URL: ${MY_BASE_URL:-https://api.example.com}
```

### The network: two options

The `agent-network` in `docker-compose.yml` is how your agent finds and is found by the rest of the platform. The correct configuration depends on where your agent lives.

#### Option A — External repository (own repo, own Compose project)

Your agent's `docker-compose.yml` is separate from the platform's. When the platform starts, it creates a Docker network named `prometheus_platform_agent-network`. Your agent needs to join that existing network:

```yaml
networks:
  agent-network:
    external: true
    name: prometheus_platform_agent-network
```

`external: true` means "this network was created by someone else; don't try to create it yourself." The `name` must match what the platform actually created.

> **Note:** The network name is `<COMPOSE_PROJECT_NAME>_agent-network`. The platform defaults to `prometheus_platform` (the directory name), giving `prometheus_platform_agent-network`. If your platform team changed `COMPOSE_PROJECT_NAME`, update the `name` field accordingly.

Start your agent after the platform is running:

```bash
# In the platform directory:
make up

# In your agent directory:
docker compose up --build
```

#### Option B — In-tree (agent lives inside `prometheus_platform/agents/`)

If you want your agent to be part of the main platform stack and launched by `make up`, copy your project directory into `prometheus_platform/agents/<your-agent-name>/`. The platform's Makefile automatically discovers any `docker-compose.yml` inside `agents/*/`.

In this case, the platform's `docker-compose.yml` owns the network definition. Your agent just references it by name:

```yaml
networks:
  agent-network:
```

(No `external:` or `name:` — just the name, referencing the network defined in the parent compose.)

Then, from the `prometheus_platform` directory:

```bash
make generate   # re-discovers agents and regenerates docker-compose.agents.yml
make up         # starts everything including your new agent
```

**Which option to choose?**

| Scenario | Recommended option |
|----------|-------------------|
| Agent is developed by a separate team or has its own release cycle | Option A — own repo |
| Multiple related agents share a single repo / are deployed together | Option A — shared repo with one `docker-compose.yml` listing all services |
| Agent is a general-purpose utility that ships with the platform | Option B — in-tree |

Most purpose-built agents use Option A. Option B is mainly for agents maintained alongside the platform itself.

---

## Step 8 — Running locally

You have two ways to run your agent during development. Use Python for fast iteration, Docker for integration testing.

### Option A: Python directly (no Docker)

This is the fastest way to test your logic. Set your environment variables and run:

```bash
# Load your .env file into the shell
export $(grep -v '^#' .env | xargs)

# Run the agent (the base class starts uvicorn on AGENT_PORT)
python agent.py
```

The agent starts and logs something like:

```
INFO:prometheus_api.agent.base:Loaded agent card: My Agent v1.0.0
INFO:prometheus_api.agent.base:Starting HTTP server on 0.0.0.0:8000
```

To test it, send a request in a second terminal:

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
        "parts": [{"kind": "text", "text": "{\"input_text\": \"hello world\"}"}]
      },
      "metadata": {"skillId": "my_skill"}
    }
  }' | python -m json.tool
```

You'll see the response with your result dict in the final `completed` status event.

> **Tip:** When running locally without a Redis connection, the agent still works — artifact registry and state storage fall back to an in-memory dict. Set `AGENT_SECRET_REQUIRED=false` in `.env` to skip the bearer token check during development.

### Option B: Docker Compose

Build and start the container:

```bash
docker compose up --build
```

The `--build` flag rebuilds the image if your code or `pyproject.toml` has changed. Omit it for fast restarts when nothing changed.

Stop with `Ctrl+C`, or in the background:

```bash
docker compose up --build -d    # detached (runs in background)
docker compose logs -f          # follow logs
docker compose down             # stop and remove container
```

---

## Step 9 — Deploying to the platform

Once your agent works locally, deploying it means connecting it to a running Prometheus platform instance so the orchestrator can discover and route to it.

### What happens at startup

When your container starts, `PrometheusAgent.run()` calls `register_with_registry_async()`. This sends a POST request to `REGISTRY_URL` (the LiteLLM proxy) advertising your agent's name, URL, and skills. The orchestrator polls LiteLLM's agent list and starts routing requests to you.

Registration retries with exponential backoff (default: 10 attempts, up to 30 seconds between tries), so the order in which containers start does not matter — your agent will wait for LiteLLM to become available.

### Option A: External repository

1. Make sure the platform is running (`make up` from `prometheus_platform/`).
2. Fill in your `.env` with the same `AGENT_SECRET`, `LITELLM_MASTER_KEY`, `REDIS_PASSWORD`, and `REGISTRY_URL` values that the platform uses (copy from `prometheus_platform/.env`).
3. Start your agent: `docker compose up --build -d`
4. Verify registration: `curl -s http://localhost:9977/v1/agents | python -m json.tool` (replace `9977` with `LITELLM_LOCAL_PORT` from the platform's `.env`). Your agent's name should appear in the list.

If you need the agent to restart automatically when the platform does, add it to the platform team's infrastructure configuration or document the startup order for your deployment environment.

### Option B: In-tree

1. Copy your project directory to `prometheus_platform/agents/<your-agent-name>/`.
2. In your agent's `docker-compose.yml`, switch to the in-tree network configuration (see Step 7, Option B).
3. From `prometheus_platform/`:
   ```bash
   make generate   # picks up your new docker-compose.yml
   make up         # or make restart if platform is already running
   ```
4. Your agent appears in `docker compose ps` and logs with `make logs SERVICE=your-agent-name`.

> **Note:** The platform's `make generate` discovers agents by looking for `docker-compose.yml` files at exactly one directory level inside `agents/`. The directory name becomes the service name. Make sure your directory name is distinct from existing agents.

---

## Advanced topics

The following capabilities are documented in detail in the linked references. This section shows where to look.

### Emitting artifacts

Instead of (or in addition to) returning a dict, your agent can emit typed artifacts that the frontend knows how to render — JSON data, files, PDFs.

```python
# Inline JSON artifact (available to downstream agents by artifact_id)
await self.send_json_artifact(
    context=context, event_queue=event_queue,
    payload={"score": 0.95, "label": "acceptable"},
    name="analysis_result",
    json_type="prometheus.my_agent.result.v1",
    catalog_artifact=True,
)
return {"message": "Analysis complete.", "agent": self.agent_name}

# File artifact (URI-backed, e.g. a local file or deeplynx:// reference)
await self.send_artifact_reference(
    context=context, event_queue=event_queue,
    name="report.pdf",
    description="Generated PDF report",
    uri="file:///tmp/report.pdf",
    mime_type="application/pdf",
)
```

See [PrometheusAgent Quick Start](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/QUICK_START.md) for the full artifact API including DeepLynx uploads.

### Multi-turn input (`INPUT_REQUIRED`)

If your agent needs information it cannot infer from the initial call, it can pause and ask the user. The base class provides `send_input_required` which renders a form in the UI:

```python
from prometheus_api.agent import MissingInput

async def _execute(self, params, context, event_queue):
    state = self.load_context_state(str(context.context_id))
    resolved = {**state.get("resolved", {}), **self.get_provided_inputs(context)}

    if "temperature_c" not in resolved:
        self.save_context_state(str(context.context_id), {"resolved": resolved})
        await self.send_input_required(
            context=context, event_queue=event_queue,
            missing_inputs=[MissingInput(
                name="temperature_c",
                description="Operating temperature in °C.",
                user_prompt="What operating temperature (°C)?",
                type="number",
                required=True,
            )],
            hint="I need an operating temperature to continue.",
        )
        return {}   # suspend — do NOT return real results here
    
    # On resume, resolved["temperature_c"] is populated
    ...
```

See the `INPUT_REQUIRED` section in [PrometheusAgent Quick Start](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/QUICK_START.md) for the full pattern and important rules.

### Multiple skills

When your agent card lists more than one skill, dispatch on `params.get("skill_id")`:

```python
async def _execute(self, params, context, event_queue):
    dispatch = {
        "analyze":  self._handle_analyze,
        "summarize": self._handle_summarize,
    }
    handler = dispatch.get(params.get("skill_id"))
    if handler is None:
        return {"error": f"Unknown skill: {params.get('skill_id')}"}
    return await handler(params, context, event_queue)
```

### DeepLynx file storage

To persist output files (CSVs, HDF5, etc.) to the DeepLynx data platform and make them accessible to other agents:

```python
from pathlib import Path
from prometheus_api.storage_client.connection import ConnectionConfig

config = ConnectionConfig.from_env()
artifact = await self.send_deeplynx_artifact(
    context=context, event_queue=event_queue,
    file_path=Path("/tmp/output.csv"),
    name="simulation_output.csv",
    description="Agent simulation results",
    storage_config=config,
    mime_type="text/csv",
)
# artifact.uri  →  "deeplynx://organizations/1/projects/2/items/42"
```

See [PrometheusAgent Quick Start — DeepLynx artifact](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/QUICK_START.md#deeplynx-artifact) and [StorageClient Guide](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/storage-client/GUIDE.md).

### Per-conversation state

If your agent needs to remember context between turns (e.g. partial results, user preferences), use the built-in state store keyed by `context_id`:

```python
state = self.load_context_state(str(context.context_id))
state["counter"] = state.get("counter", 0) + 1
self.save_context_state(str(context.context_id), state)
```

State is backed by Redis when `REDIS_URL` is set, with an in-memory fallback for local development.

---

## Further reading

| Document | Description |
|----------|-------------|
| [PrometheusAgent Guide](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/GUIDE.md) | Full API reference, pitfalls, lifecycle hooks |
| [PrometheusAgent Quick Start](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/QUICK_START.md) | Condensed recipes for every helper |
| [Environment Setup](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/ENV_SETUP.md) | All environment variables for agents and storage |
| [StorageClient Guide](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/storage-client/GUIDE.md) | Reading and writing to DeepLynx |
| [HPC Notes](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/hpc.md) | Running on INL HPC with Podman and corporate CA bundles |
| [`examples/agent_patterns.py`](https://github.inl.gov/genesis/prometheus_api/blob/main/examples/agent_patterns.py) | Runnable reference implementation |
