# PrometheusAgent Quick Start

`PrometheusAgent` is the base class for A2A-enabled specialist agents in Prometheus. You implement `_execute(...)`, return a final structured dict, and optionally emit status updates, artifacts, or `INPUT_REQUIRED` messages while the task is running.

## Install

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```

## Minimal Agent

```python
from prometheus_api.agent import EventQueue, PrometheusAgent, RequestContext


class MyAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        material_id = params.get("material_id", "").strip()
        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": f"Received material {material_id or 'unknown'}.",
        }


if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

## Minimal `agent_card.json`

Agent cards are now routing metadata only. Do not declare `inputSchema` here. Specialist agents should request missing values at runtime with `send_input_required(...)`.

```json
{
  "name": "My Agent",
  "description": "Performs specialist analysis.",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "analyze_material",
      "name": "Analyze Material",
      "description": "Performs a material analysis and requests missing inputs when needed.",
      "tags": ["materials", "analysis"]
    }
  ]
}
```

## Agent Actions

### Send Status Updates

Use status updates for transient progress UI. These are not durable chat messages.

```python
from prometheus_api.agent import EventQueue, PrometheusAgent, RequestContext


class StatusAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Loading source data.",
        )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Running analysis.",
        )

        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": "Analysis complete.",
        }
```

### Request Missing Input

Use `load_context_state(...)`, `get_provided_inputs(...)`, and `send_input_required(...)` when execution cannot continue without more user input. Persist partial state by `contextId` so follow-up submissions can resume cleanly.

```python
from prometheus_api.agent import EventQueue, MissingInput, PrometheusAgent, RequestContext


class InputRequiredAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        state = self.load_context_state(context.context_id)
        resolved = dict(state.get("resolved", {}))
        resolved.update(self.get_provided_inputs(context))
        if params.get("material_id"):
            resolved["material_id"] = params["material_id"]

        if "temperature_c" not in resolved:
            self.save_context_state(context.context_id, {"resolved": resolved})
            await self.send_input_required(
                context=context,
                event_queue=event_queue,
                missing_inputs=[
                    MissingInput(
                        name="temperature_c",
                        description="Operating temperature in degrees Celsius for the analysis case.",
                        user_prompt="What operating temperature should I use?",
                        type="number",
                    )
                ],
                hint="This analysis needs a temperature before it can proceed.",
            )
            return {}

        self.save_context_state(context.context_id, {"resolved": resolved})
        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": f"Running at {resolved['temperature_c']} C.",
        }
```

### Emit a File Artifact

Use `send_artifact_reference(...)` for files or externally addressable resources.

```python
from pathlib import Path


class FileArtifactAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        report_path = Path("/tmp/report.pdf")

        artifact = await self.send_artifact_reference(
            context=context,
            event_queue=event_queue,
            name="report.pdf",
            description="Generated report",
            uri=f"file://{report_path}",
            mime_type="application/pdf",
        )

        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": "Report created successfully.",
            "new_artifacts": [artifact.to_dict()],
        }
```

### Emit an Inline JSON Artifact

Use `send_json_artifact(..., catalog_artifact=True)` for reusable structured data.

```python
class JsonArtifactAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        artifact_id = await self.send_json_artifact(
            context=context,
            event_queue=event_queue,
            name="thermal_result",
            description="Structured thermal analysis result",
            payload={"max_temperature_c": 650.0, "status": "acceptable"},
            json_type="prometheus.thermal_analysis.result.v1",
            catalog_artifact=True,
        )

        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": "Thermal analysis complete.",
            "artifact_id": artifact_id,
        }
```

### Emit a Durable Conversation Message

Use `send_conversation_message(...)` for messages that should appear in chat history in addition to your final response.

```python
await self.send_conversation_message(
    context=context,
    event_queue=event_queue,
    message="Conversion started.",
)
```

## Suggested Data-Fetching Patterns

### Initialize service clients in `__init__`

Create reusable clients once and keep `_execute(...)` focused on request handling:

```python
from prometheus_api.storage_client import ConnectionConfig, StorageClient


class StorageBackedAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = StorageClient(ConnectionConfig.from_env())
```

### Fetch authoritative data inside `_execute(...)`

Read external systems during execution using the current request inputs and context state:

```python
    async def _execute(self, params, context, event_queue):
        item = self.storage.items.get(params["item_id"])
        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": f"Loaded {item.name}.",
            "item": {"id": item.id, "name": item.name},
        }
```

### Persist only execution state in `ContextStateStore`

Use `save_context_state(...)` for partial progress, resolved inputs, or resume cursors. Do not copy large external records into the context store unless they are part of the agent's own execution state.

Good:
- resolved user inputs
- pagination cursors
- chosen scenario/configuration
- partial workflow progress

Avoid:
- duplicating source-of-truth rows from upstream systems
- long-lived caches that belong in a dedicated service cache
- storing secrets in plain agent context state

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port to listen on | `8000` | No |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` | No |
| `AGENT_SECRET` | Shared secret for authentication | - | Yes in production |
| `AGENT_SECRET_REQUIRED` | Enforce authentication | `true` | No |
| `REGISTRY_URL` | Registry service URL | - | No |
| `REDIS_URL` | Redis for artifact/state persistence | `redis://localhost:6379` | No |
| `AGENT_CONTEXT_TTL_SECONDS` | TTL for persisted per-context state | `86400` | No |

## Project Structure

```text
my-agent/
├── agent.py
├── agent_card.json
├── .env
├── requirements.txt
└── Dockerfile
```

## Next Steps

- [PrometheusAgent Guide](./GUIDE.md)
- [Environment Setup](../ENV_SETUP.md)
- [`examples/agent_patterns.py`](../../examples/agent_patterns.py)
