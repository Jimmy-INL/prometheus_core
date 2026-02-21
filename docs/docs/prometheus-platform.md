---
title: Platform
description: Description of page
icon: lucide/layout-dashboard
---

# Prometheus Platform

The main application -- a FastAPI backend and Chainlit frontend that together provide a chat-driven interface for triggering and monitoring engineering workflows.

## Architecture

``` mermaid
graph LR
  U[User] --> F[Chainlit Frontend]
  F -->|POST /api/chat| B[FastAPI Backend]
  B -->|chat response| F
  B -->|workflow response| F
  F -->|stream /api/demo/workflow/run| B
  B -->|NDJSON events| F
  B --> DB[(SQLite)]
```

The two services run independently and communicate over HTTP. The frontend resolves the backend URL from its `config.yml` (`platform-url` key).

| Service | Directory | Port | Stack |
|---------|-----------|------|-------|
| Backend | `prometheus_platform/backend/` | 8001 | FastAPI, aiosqlite, uvicorn |
| Frontend | `prometheus_platform/frontend/` | default | Chainlit, VTK, pyyaml |

## Getting started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Install and run

```bash
# Install dependencies
cd prometheus_platform/backend && uv sync --group dev
cd ../frontend && uv sync --group dev

# Terminal 1 -- start the backend
cd prometheus_platform/backend
make run        # FastAPI dev server on :8001

# Terminal 2 -- start the frontend
cd prometheus_platform/frontend
make run        # Chainlit UI
```

Log in with `admin` / `admin`.

### Common commands

All commands run from within `backend/` or `frontend/`:

```bash
make run        # Start the service
make test       # Run pytest
make lint       # Ruff linter (report only)
make format     # Ruff formatter check
make fix        # Auto-fix lint + format
make check      # All checks (lint + format + typecheck via mypy)
```

Run a single test:

```bash
uv run pytest tests/test_chat.py       # By file
uv run pytest -k test_name             # By name
```

## Configuration

The frontend reads `frontend/config.yml`:

```yaml
chat-intro: "Welcome to the Prometheus Platform."
chat-suggestion-title: "What would you like to do today?"

workflow-suggestions:
  - "I want to design a reactor primary coolant system."
  - "Run FTL Safety Analysis"

local-users:
  - username: "admin"
    password: "admin"
    role: "admin"

platform-url: "http://127.0.0.1:8001"
debug: true
auto-approve-steps: true

agent-names:
  - "MOOSE"
  - "Alchemy"
  - "AutoDONE"
  - "FTL"
```

Override the config path with `PROMETHEUS_CONFIG_PATH=/path/to/config.yml`.

## API endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message. Returns a `chat` or `workflow` response type. |

Request body:

```json
{
  "message": "string",
  "user_id": "string",
  "session_id": "optional string",
  "context": {},
  "files": []
}
```

If the message matches a workflow suggestion from `config.yml`, the response includes `workflow_id` and `workflow_type`. Otherwise it returns a plain chat reply.

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions/{session_id}` | Session metadata |
| GET | `/api/sessions/{session_id}/messages` | Messages in a session (chronological) |
| GET | `/api/sessions/{session_id}/workflow-steps` | Workflow steps in a session |
| GET | `/api/sessions/user/{user_id}` | All sessions for a user (newest first) |

### Demo content

| Method | Path | Description |
|--------|------|-------------|
| GET | `/demo/autodone` | AutoDONE dynamic form definition |
| GET | `/demo/ifc` | Sample IFC building model |
| GET | `/demo/exodus` | Sample Exodus mesh file |
| GET | `/demo/ecar` | Sample ECAR PDF report |

### Workflow streaming

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/demo/workflow/run` | Execute the demo workflow, streaming NDJSON events |

Events are streamed line-by-line as JSON objects with `event_type`:

- `workflow_start` -- total step count
- `step_start` -- step name, agent
- `step_complete` -- response text, optional `artifact_url`
- `workflow_complete` -- final event

## Data flow

### Chat flow

1. User sends a message in the Chainlit UI
2. Frontend POSTs to `/api/chat`
3. Backend checks if the message matches a workflow trigger
4. Returns either `chat` (displayed directly) or `workflow` (triggers streaming)

### Workflow execution

1. Frontend initiates a stream to `/api/demo/workflow/run`
2. Backend executes 5 predefined steps sequentially, each with a simulated delay:
    - **Planning** (Orchestrator) -- creates the workflow plan
    - **Requirements** (Requirements Agent) -- generates system requirements
    - **Architecture** (Systems Architecture Agent) -- extracts system functions
    - **3D model** (Alchemy Agent) -- generates an IFC model (artifact: `/demo/ifc`)
    - **ECAR report** (ECAR Agent) -- generates a PDF report (artifact: `/demo/ecar`)
3. Frontend renders each step as a `cl.Step` and fetches artifacts at completion

### File upload

The frontend detects file type on upload and processes locally:

- `.e` / `.exo` (Exodus) -- VTK processing, rendered with ExodusViewer
- `.ifc` -- copied to `public/ifc-data/`, rendered with IFCViewer
- `.pdf` -- displayed inline

## Database

SQLite via aiosqlite at `backend/data/prometheus.db` (auto-created on startup).

### Schema

**sessions**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | Primary key |
| user_id | TEXT | Indexed |
| created_at | TEXT | ISO 8601 UTC |
| updated_at | TEXT | ISO 8601 UTC |

**messages**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | Primary key |
| session_id | TEXT | FK to sessions |
| role | TEXT | `user` or `assistant` |
| content | TEXT | |
| response_type | TEXT | `chat` or `workflow` |
| metadata | TEXT | JSON string |
| created_at | TEXT | ISO 8601 UTC |

**workflow_steps**

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT | Primary key |
| session_id | TEXT | FK to sessions |
| workflow_id | TEXT | Indexed |
| step_name | TEXT | |
| step_type | TEXT | |
| status | TEXT | `pending`, `running`, `completed`, `failed` |
| input_data | TEXT | JSON string |
| output_data | TEXT | JSON string |
| error_message | TEXT | |
| started_at | TEXT | |
| completed_at | TEXT | |
| created_at | TEXT | ISO 8601 UTC |

There is no migration tool. Delete `prometheus.db` to reset the schema.

## Backend patterns

### State repository

Persistence uses the repository pattern:

- `state/base.py` -- `StateRepository` abstract base class
- `state/sqlite.py` -- `SQLiteStateRepository` implementation

The repo is initialized during the FastAPI lifespan and stored on `app.state.repo`. Routers access it via `request.app.state.repo`.

### Pydantic models

Models are split by purpose:

| File | Contains |
|------|----------|
| `models/chat.py` | `ChatMessageRequest`, `ChatResponse`, `ResponseType` enum |
| `models/state.py` | `SessionRecord`, `MessageRecord`, `WorkflowStepRecord` |
| `models/dynamic_form.py` | `FormField`, `DynamicFormProps`, field helper functions |

### Dynamic forms

The `dynamic_form.py` module provides a form definition system used by the frontend's `DynamicForm.jsx` component. Supported input types: `text`, `textarea`, `select`, `checkbox`, `number`, `email`, `password`, `date`, `datetime`. Helper functions (`create_text_field`, `create_select_field`, etc.) simplify field construction.

## Frontend components

### Custom React elements

Located in `frontend/public/elements/`, rendered via Chainlit's `cl.CustomElement`:

| Component | Purpose |
|-----------|---------|
| `DynamicForm.jsx` | Configurable forms with validation, timeout countdown, help text |
| `IFCViewer.jsx` | 3D building model viewer (ThatOpen engine, THREE.js) |
| `ExodusViewer.jsx` | VTK-based mesh visualization with playback controls and color presets |
| `FollowUpSuggestions.jsx` | Clickable workflow suggestion cards |
| `MermaidViewer.jsx` | Diagram renderer |

### Message handler

`components/message_handler.py` is the central router for incoming messages. It determines whether to process a file upload locally, forward a text message to the backend, or initiate workflow streaming.

### Settings handler

`components/settings_handler.py` configures the Chainlit sidebar with tabs for model selection, agent toggles, and debug features (form testing, file viewer testing).

## Code style

- Line length: 120
- Linter/formatter: ruff (rules: E, F; E501 ignored)
- Type checker: mypy
- Tests: pytest with pytest-asyncio (`asyncio_mode = "auto"`)
