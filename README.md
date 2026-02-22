# Prometheus Platform

A workflow orchestration platform for engineering design. Users interact through a chat interface that can trigger multi-step workflows (e.g., reactor coolant system design), upload and visualize 3D files (IFC, Exodus), and view generated reports.

The platform is split into three services:

- **Backend** -- FastAPI REST API that manages sessions, chat, and workflow execution
- **Frontend** -- Chainlit chat UI that communicates with the backend and renders custom viewers
- **Docs** -- Static documentation that is turned into a Github pages site with CI/CD.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Getting Started

Both services need to be running. The backend must start first since the frontend calls it.

### 1. Install dependencies

```bash
cd backend
uv sync

cd ../frontend
uv sync
```

To include dev dependencies (pytest, ruff, mypy):

```bash
uv sync --group dev
```

### 2. Start the backend

```bash
cd backend
make run
```

This starts the FastAPI server on port 8001. The SQLite database is created automatically at `backend/data/prometheus.db` on first run.

### 3. Start the frontend

In a separate terminal:

```bash
cd frontend
source .venv/bin/activate
chainlit create-secret | sed '1d' > .env
make run
```

This starts the Chainlit server. Open the URL shown in the terminal output to access the chat interface.

### 4. Log in

Default credentials (defined in `frontend/config.yml`):

- Username: `admin`
- Password: `admin`

## Configuration

The frontend is configured via `frontend/config.yml`:

| Key | Description |
|-----|-------------|
| `platform-url` | Backend API URL (default: `http://127.0.0.1:8001`) |
| `debug` | Enable debug features in the UI settings panel |
| `auto-approve-steps` | Skip manual approval between workflow steps |
| `workflow-suggestions` | Chat suggestions shown on startup |
| `agent-names` | Agents available in the settings panel |
| `local-users` | Username/password pairs for local auth |

The config file path can be overridden with the `PROMETHEUS_CONFIG_PATH` environment variable.

## Development

### Running tests

```bash
# Backend
cd backend
make test

# Frontend
cd frontend
make test
```

Run a single test file:

```bash
uv run pytest tests/test_chat.py
```

Run a single test by name:

```bash
uv run pytest -k test_name
```

### Linting and formatting

```bash
# Check for issues
make lint
make format

# Auto-fix
make fix

# Run all checks (lint + format + typecheck)
make check
```

### Type checking

```bash
make typecheck
```

## Project Structure

```
backend/
  main.py           # FastAPI app entry point
  routers/          # API route handlers
  models/           # Pydantic models
  orchestrator/     # Workflow execution logic
  state/            # Database layer (SQLite via aiosqlite)
  data/             # SQLite DB and sample files (IFC, Exodus, PDF)
  tests/

frontend/
  main.py           # Chainlit app entry point
  config.yml        # Application configuration
  components/       # Message handling, file processing, settings
  utils/            # Settings loader
  public/elements/  # Custom React components (JSX)
  public/js/        # Bundled JS for IFC and VTK viewers
  tests/
```
