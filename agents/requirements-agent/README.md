# Plant Requirements Agent

A Prometheus A2A agent that wraps the `nucsys_agent` nuclear system design and requirements package.

## Capabilities

Exposes six skills via the A2A protocol, all routed through a single `action` parameter:

| Action | Description |
|--------|-------------|
| `design` | One-shot nuclear loop design from natural language |
| `design_chat` | Stateless multi-turn conversational loop design |
| `requirements` | One-shot component requirements filtering |
| `requirements_chat` | Stateless multi-turn requirements conversation |
| `requirements_from_design` | Requirements seeded from a sized design node |
| `audit` | Engineering model audit Q&A |

### Domain Details

- **Loop Design**: Deterministic thermodynamic/hydraulic sizing for PWR primary loops and BOP Rankine cycles. Supports water, sodium, CO₂, and helium coolants. Outputs Alchemy-format topology graphs.
- **Requirements**: ~1,500 baseline requirements across 6 component types (pump, valve, condenser, steam_generator, pressurizer, turbine). Filters applicable requirements based on component profile.
- **Audit**: Keyword-matched Q&A over documented engineering correlations, fluid property sources, sizing assumptions, and references.

## Setup

### Install

```bash
cp .env.example .env
# Edit .env: set AGENT_SECRET and any LLM API keys
pip install -r requirements.txt
pip install -e .          # registers the nucsys-agent CLI command
```

For diagram support in the CLI and Streamlit app:
```bash
pip install -e ".[diagram]"   # adds matplotlib
```

### A2A Agent (Prometheus platform)

```bash
python agent.py
```

### Docker

```bash
docker build -t plant-requirements-agent .
docker run -p 8000:8000 --env-file .env plant-requirements-agent
```

For multi-agent deployments with matching ports:
```bash
docker run -p 8001:8001 -e AGENT_PORT=8001 -e AGENT_HOST=requirements-agent --env-file .env plant-requirements-agent
```

## Interactive CLI

The `nucsys-agent` command opens a full interactive menu for design, requirements, diagrams, and model audit — no A2A protocol or network required.

```bash
nucsys-agent                                    # open interactive menu
nucsys-agent "300 MWth PWR primary loop"        # one-shot design, then menu
nucsys-agent "300 MWth PWR primary loop" -i     # conversational design, then menu
nucsys-agent -f alchemy_out.json                # load saved design → requirements + diagram
```

Without installing (run from the `requirements_agent/` directory):
```bash
python -m nucsys_agent.cli
```

### Menu options

| Key | Action |
|-----|--------|
| `D` | Design a new loop (conversational) |
| `L` | Load an existing design file (`.json`) |
| `Q` | Generate component requirements for a sized node |
| `V` | View / export single-line diagram (PDF, SVG, PNG) |
| `A` | Audit engineering models — ask free-text questions |
| `H` | Help / quick reference |
| `E` | Exit |

At any prompt, type `back` to return to the menu, `exit` to quit, or `help` for a reference card.

### CLI workflow

1. **Design** — describe your system in plain English; the agent asks follow-up questions, presents the proposed topology and operating parameters (which you can adjust), runs the sizing pipeline, and saves `alchemy_out.json`.
2. **Requirements** — pick any sized component from the current design; the agent pre-fills numeric parameters and asks only for classification fields (code class, safety category, seismic category, environment). Saves a `<component>_reqs.json` instance file.
3. **Diagram** — renders an IEC-60617 / IEEE-315 single-line diagram, optionally overlaid with requirement badges. Export to PDF, SVG, or PNG.
4. **Audit** — keyword-matched Q&A over every engineering correlation, fluid property source, and reference used in the sizing calculations. Type `list` to see all available topics.

---

## Streamlit Web App

A browser-based UI covering all four capabilities. Runs locally against the same `nucsys_agent` package — no A2A agent or network needed.

```bash
streamlit run streamlit_app/app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

### Tabs

| Tab | Description |
|-----|-------------|
| **💬 Design Chat** | Conversational loop design with inline parameter and component editors |
| **📐 Diagram** | Interactive single-line diagram with normal / blueprint styles and export |
| **📋 Requirements** | Classification forms per component with numeric pre-fill from the design |
| **🔍 Model Audit** | Free-text Q&A chat over all engineering models and references |

### Sidebar

- **LLM Configuration** — select provider (Anthropic / OpenAI / none), enter your API key, and test the connection. All thermodynamic sizing is deterministic; the LLM is only used for natural language spec parsing.
- **Load existing design** — upload a saved `alchemy_db` JSON to resume requirements or diagram without re-running the design.
- **Session** — shows the active design summary and resets the session.

---

## Tests

### Install test dependencies

```bash
pip install -e ".[dev]"    # adds pytest, fastapi, httpx
```

### Run all tests

```bash
pytest tests/ -v
```

### Test files

| File | What it covers |
|------|----------------|
| `test_requirements.py` | Requirements loader, applicability engine, filter, and full conversation flow |
| `test_conversation.py` | Design conversation phases, parameter/component review, property overrides |
| `test_primary_loop.py` | End-to-end loop design pipeline and Alchemy export validation |
| `test_chat_endpoint.py` | FastAPI `/chat`, `/design`, and `/requirements/chat` endpoints (requires `fastapi`) |

Run a single file or test:
```bash
pytest tests/test_requirements.py -v
pytest tests/test_conversation.py::test_design_review_done_finalises -v
```

> **Note:** `test_chat_endpoint.py` tests the `nucsys_agent.server` FastAPI interface directly (not the A2A layer). It requires `fastapi` from the `[dev]` extras.

---

## A2A Message Format

All requests follow JSON-RPC 2.0. The `parts[0].text` field must be a JSON string containing `action` and any required parameters.

```bash
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <AGENT_SECRET>" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "req-1",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [
          {"text": "{\"action\": \"design\", \"query\": \"300 MWth PWR primary loop\"}"}
        ]
      }
    }
  }'
```

## Skill Examples

### design — One-Shot Loop Design

```json
{
  "action": "design",
  "query": "300 MWth PWR primary loop"
}
```

Returns `spec`, `alchemy_db`, `validation_issues`, `export_issues`.

---

### design_chat — Conversational Design (First Turn)

```json
{
  "action": "design_chat",
  "initial_query": "500 MWth sodium-cooled reactor",
  "history": []
}
```

Returns `agent_reply`, `phase`, `is_done`. Repeat with growing `history` until `is_done` is true.

---

### requirements — One-Shot Requirements

```json
{
  "action": "requirements",
  "component_type": "pump",
  "profile": {
    "code_class": "Class 1",
    "safety_category": "safety-related",
    "seismic_category": "I",
    "flow_rate_kg_s": 1850,
    "delta_p_MPa": 0.45
  }
}
```

Returns `applicable_requirements`, `tbd_requirements`, and a validation summary.

---

### requirements_from_design — Requirements from a Design Node

```json
{
  "action": "requirements_from_design",
  "node_name": "Primary Sink",
  "node_props": {
    "m_dot_kg_s": 1847.3,
    "delta_p_MPa": 0.44,
    "shaft_power_MW": 3.2,
    "canonical_type": "primary_pump"
  },
  "history": []
}
```

On first turn the agent will only ask classification questions; numeric fields are pre-filled from the node properties.

---

### audit — Engineering Model Q&A

```json
{
  "action": "audit",
  "question": "How is the steam generator sized?"
}
```

Or list all available topics:
```json
{
  "action": "audit",
  "question": "list"
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_PORT` | Port the agent listens on | `8000` |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` |
| `AGENT_SECRET` | Shared Bearer token secret (required in production) | — |
| `REGISTRY_URL` | Agent registry URL | `http://registry:8000` |
| `ANTHROPIC_API_KEY` | Enables Anthropic LLM spec parsing (optional) | — |
| `OPENAI_API_KEY` | Enables OpenAI LLM spec parsing (fallback, optional) | — |

Without an LLM API key the agent falls back to regex-based spec parsing, which handles common formats like `"300 MWth PWR"`.

## Directory Structure

```
requirements_agent/
├── agent.py              # A2A agent entrypoint (PlantRequirementsAgent)
├── agent_card.json       # Agent metadata and skill definitions
├── Dockerfile            # Container configuration
├── requirements.txt      # Runtime Python dependencies
├── pyproject.toml        # CLI entry point + optional dev/diagram extras
├── .env.example          # Environment configuration template
├── README.md             # This file
├── streamlit_app/
│   ├── app.py            # Streamlit web UI (design, diagram, requirements, audit)
│   └── requirements.txt  # Streamlit-specific dependencies
├── tests/
│   ├── test_requirements.py    # Requirements engine unit + integration tests
│   ├── test_conversation.py    # Design conversation phase tests
│   ├── test_primary_loop.py    # End-to-end pipeline + export validation
│   └── test_chat_endpoint.py   # FastAPI server endpoint tests
└── nucsys_agent/         # Nuclear system design & requirements package
    ├── cli.py             # Interactive CLI (nucsys-agent command)
    ├── server.py          # FastAPI REST server (nucsys_agent standalone)
    ├── workflow.py        # Loop design pipeline (run_agent)
    ├── conversation.py    # Stateless conversational design
    ├── config.py          # Agent configuration (pydantic-settings)
    ├── models.py          # Pydantic data models (Node, Building, DesignSpec)
    ├── spec_parser.py     # Natural language → DesignSpec (LLM / regex)
    ├── ontology.py        # Component type definitions
    ├── validator.py       # Design validation
    ├── requirements/      # Requirements filtering engine
    ├── sizing/            # Thermodynamic & hydraulic calculations
    ├── audit/             # Engineering model audit engine
    ├── llm/               # LLM clients (Anthropic, OpenAI)
    ├── rag/               # Card store & retrieval
    ├── serializer/        # Alchemy JSON serialization
    ├── visualization/     # P&ID single-line diagrams (optional)
    └── data/              # Baselines, schemas, cards, ontology
```
