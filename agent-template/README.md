# Prometheus Agent Template

A template for building specialist agents for the [Prometheus](https://github.inl.gov/genesis/prometheus_platform)
multi-agent platform. Agents speak the Agent-to-Agent (A2A) protocol; the
platform's orchestrator discovers them, routes user requests to them, and renders
their responses in the Chainlit UI.

This repository gives you two things:

- **`agent_template/`** — the canonical set of files for one agent
  (`agent.py`, `agent_card.json`, `pyproject.toml`, `Dockerfile`,
  `docker-compose.yml`, `.env.example`).
- **`setup_agent.py`** — an interactive scaffolder that copies the template into
  a new directory with your agent's name, slug, class, and skill filled in.
- **[`TUTORIAL.md`](TUTORIAL.md)** — a step-by-step guide that explains every file
  and walks you through building, containerizing, and deploying an agent.

Each agent builds **`FROM`** the prebuilt `prometheus_api` base image, which
already bundles Python 3.12, `prometheus_api`, and the A2A server stack
(`a2a`, `starlette`, `uvicorn`). Your image only adds your code and any extra
dependencies — builds are small and fast.

## Quick start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker Desktop (or Podman) — for containerized runs
- Access to the `prometheus_api` base image registry
  (`containers.github.inl.gov/genesis/prometheus_api`)

### Scaffold a new agent

```bash
git clone git@github.inl.gov:genesis/prometheus_agent_template.git
cd prometheus_agent_template
python setup_agent.py
```

The script prompts for the agent name, description, slug, class name, and primary
skill, then writes a ready-to-edit project to the output directory you choose:

```
my-agent/
├── agent.py
├── agent_card.json
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

> Prefer to do it by hand? Copy `agent_template/` and replace the `TEMPLATE_*`
> placeholders yourself. See [`TUTORIAL.md`](TUTORIAL.md).

### Run it

```bash
cd my-agent
cp .env.example .env          # fill in real values

# Local (fast iteration):
uv venv && source .venv/bin/activate
uv pip install git+https://github.inl.gov/genesis/prometheus_api.git
AGENT_SECRET_REQUIRED=false python agent.py

# Or with Docker (set PROMETHEUS_API_BASE_IMAGE_HASH in .env first):
docker compose up --build
```

See the generated `README.md` in your agent directory, and
[`TUTORIAL.md`](TUTORIAL.md) for the full walkthrough — agent card design,
emitting artifacts, multi-turn input (`INPUT_REQUIRED`), multiple skills,
DeepLynx storage, and both deployment paths (external repo vs. in-tree).

## Repository development

This repository's own tooling (the scaffolder) is uv-managed:

```bash
make check      # ruff lint + format check + mypy
make fix        # auto-fix lint + format
make test       # pytest
```

## Further reading

These live in the [`prometheus_api`](https://github.inl.gov/genesis/prometheus_api) repository:

| Document | Description |
|----------|-------------|
| [PrometheusAgent Guide](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/GUIDE.md) | Full API reference, pitfalls, lifecycle hooks |
| [PrometheusAgent Quick Start](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/agent/QUICK_START.md) | Condensed recipes for every helper |
| [Environment Setup](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/ENV_SETUP.md) | All environment variables for agents and storage |
| [StorageClient Guide](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/storage-client/GUIDE.md) | Reading and writing to DeepLynx |
| [HPC Notes](https://github.inl.gov/genesis/prometheus_api/blob/main/docs/hpc.md) | Running on INL HPC with Podman and corporate CA bundles |

## Support

Reach out on Teams.
