# PrometheusAgent Guide

## Overview

`PrometheusAgent` is the base class for A2A-enabled specialist agents in Prometheus. It handles:

- loading and serving the agent card
- authentication middleware
- registry registration
- A2A request handling and task execution
- final status emission from your returned dict
- helper methods for status updates, artifacts, durable chat messages, and `INPUT_REQUIRED`
- conversation artifact registration
- per-agent context state persistence keyed by `contextId`

You implement `_execute(params, context, event_queue)` and use the helpers when you need richer behavior.

## Core Contract

### 1. Return the final structured response from `_execute(...)`

The canonical final result is the dict you return.

```python
return {
    "conversation_id": context.context_id,
    "status": "completed",
    "message": "Thermal analysis complete.",
}
```

The base executor emits that payload in the final `TaskStatusUpdateEvent`:

- `status.state = completed`
- `status.message.parts[*].text = json.dumps(return_value)`

Do not wrap the final result in a synthetic artifact unless you specifically need a separate artifact stream.

### 2. Use agent cards for routing metadata only

`agent_card.json` should describe what the agent does. It should not declare `inputSchema` for orchestrator-side form generation.

```json
{
  "name": "Thermal Agent",
  "description": "Performs thermal analyses and requests missing operating conditions at runtime.",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "analyze_thermal",
      "name": "Analyze Thermal",
      "description": "Runs a thermal analysis for a material and requests any missing operating inputs.",
      "tags": ["thermal", "materials", "analysis"]
    }
  ]
}
```

### 3. Let the specialist own missing-input logic

If the agent cannot proceed, it should emit `INPUT_REQUIRED` itself. The orchestrator can help resolve values from shared context, but the subagent remains authoritative about what is still missing.

## Minimal Agent

```python
from prometheus_api.agent import EventQueue, PrometheusAgent, RequestContext


class MyAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue):
        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": "Request handled.",
        }


if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

## Agent Actions

### Send Progress Status

Use `send_status_update(...)` for transient progress messages shown while work is happening.

```python
await self.send_status_update(
    context=context,
    event_queue=event_queue,
    message="Loading source data.",
)
```

You can emit as many intermediate status updates as needed. In most cases you should not emit the final completed status manually; the base class handles that from your return value.

### Emit a Text Artifact

Use `send_text_artifact(...)` for streaming or ad hoc textual artifacts.

```python
artifact_id = await self.send_text_artifact(
    context=context,
    event_queue=event_queue,
    name="progress.log",
    text="phase=loading\n",
    last_chunk=False,
)

await self.send_text_artifact(
    context=context,
    event_queue=event_queue,
    name="progress.log",
    artifact_id=artifact_id,
    append=True,
    text="phase=complete\n",
    last_chunk=True,
)
```

### Emit a File Artifact

Use `send_artifact_reference(...)` for generated files or externally addressable resources.

```python
artifact = await self.send_artifact_reference(
    context=context,
    event_queue=event_queue,
    name="report.pdf",
    description="Generated corrosion report",
    uri="file:///tmp/report.pdf",
    mime_type="application/pdf",
)
```

This:

- emits a native A2A `file` artifact part
- registers the file in the conversation artifact catalog
- returns a normalized `ArtifactReference`

### Emit an Inline JSON Artifact

Use `send_json_artifact(...)` for structured non-file outputs.

```python
artifact_id = await self.send_json_artifact(
    context=context,
    event_queue=event_queue,
    name="thermal_result",
    description="Structured thermal analysis result",
    payload={
        "status": "acceptable",
        "max_temperature_c": 650.0,
    },
    json_type="prometheus.thermal_analysis.result.v1",
    catalog_artifact=True,
)
```

Recommended usage:

- set `catalog_artifact=True` when downstream agents or the frontend should be able to reuse the artifact
- set `json_type` for frontend visualization routing
- keep the final conversational summary in your returned dict, not only in the artifact

### Emit a Durable Conversation Message

Use `send_conversation_message(...)` when a message should appear in chat history but should not be treated as a reusable file/data artifact.

```python
await self.send_conversation_message(
    context=context,
    event_queue=event_queue,
    message="Artifact generation started.",
)
```

### Request More Input

Use `send_input_required(...)` with `MissingInput` entries when the user must provide additional values.

```python
from prometheus_api.agent import MissingInput


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
    hint="This analysis needs an operating temperature before it can continue.",
)
return {}
```

The emitted final task status has:

- `status.state = input_required`
- `status.message.parts[0] = DataPart(...)`
- canonical payload shape:

```json
{
  "missing_inputs": [
    {
      "name": "temperature_c",
      "description": "Operating temperature in degrees Celsius for the analysis case.",
      "user_prompt": "What operating temperature should I use?",
      "type": "number",
      "options": null,
      "resolvable_from_context": false,
      "sensitive": false
    }
  ],
  "hint": "This analysis needs an operating temperature before it can continue."
}
```

## Stateful Resume by `contextId`

Specialist agents should persist their own partial state keyed by the A2A `contextId`.

Use:

- `load_context_state(context.context_id)`
- `save_context_state(context.context_id, state)`
- `get_provided_inputs(context)`

Example:

```python
from prometheus_api.agent import EventQueue, MissingInput, PrometheusAgent, RequestContext


class ThermalAgent(PrometheusAgent):
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
                hint="Thermal analysis requires an operating temperature.",
            )
            return {}

        self.save_context_state(context.context_id, {"resolved": resolved})

        temperature_c = float(resolved["temperature_c"])
        material_id = resolved["material_id"]
        return {
            "conversation_id": context.context_id,
            "status": "completed",
            "message": f"Thermal analysis complete for {material_id} at {temperature_c} C.",
        }
```

Use the context store for:

- resolved user inputs
- partial execution progress
- resumable cursors or workflow position
- small derived values needed for the next turn

Do not use it as a general-purpose cache for large external records.

## Suggested Data-Fetching Patterns

### Initialize clients once

Create durable clients in `__init__` and reuse them:

```python
from prometheus_api.storage_client import ConnectionConfig, StorageClient


class StorageBackedAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = StorageClient(ConnectionConfig.from_env())
```

### Fetch authoritative data inside `_execute(...)`

Use request parameters and resolved inputs to query upstream systems during execution:

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

### Prefer small execution state over large cached payloads

Good patterns:

- persist the selected `item_id`, not the entire upstream row
- persist the resolved `temperature_c`, not a large transient report object
- persist cursor/token/checkpoint values needed to resume

Avoid:

- copying upstream source-of-truth records into context state
- storing secrets in context state
- using context state as a substitute for a real service cache

### Separate user-facing artifacts from internal fetches

If fetched data should be reusable or inspectable, emit it as an artifact. If it is only an internal lookup needed to produce the final answer, keep it internal.

Good:

- emit a generated report as a file artifact
- emit a structured result matrix as a JSON artifact
- keep raw lookup tables internal unless the user or downstream agents need them

## API Reference

### `PrometheusAgent.__init__(agent_name, agent_card_path=None)`

Parameters:

- `agent_name`: display and logging name
- `agent_card_path`: optional path to `agent_card.json`

### `_execute(params, context, event_queue)`

Override this in your subclass.

Parameters:

- `params`: parameters extracted from the incoming request
- `context`: A2A request context with `task_id`, `context_id`, and message parts
- `event_queue`: queue used to emit status and artifact events

Returns:

- final structured response dict

### `send_status_update(context, event_queue, state=TaskState.working, final=False, message=None, metadata=None)`

Emit a task status update.

### `send_text_artifact(context, event_queue, text, name="result", artifact_id=None, append=False, last_chunk=None, metadata=None)`

Emit a text artifact, optionally chunked.

### `send_json_artifact(context, event_queue, payload, name="result", description=None, json_type=None, catalog_artifact=False, artifact_id=None, append=False, last_chunk=None, metadata=None)`

Emit a native A2A data artifact. Use `catalog_artifact=True` if the artifact should be registered for later reuse.

### `send_artifact_reference(context, event_queue, name, description, uri, mime_type=None, size_bytes=None, artifact_id=None, tags=None, metadata=None)`

Register and emit a URI-backed file artifact.

### `send_conversation_message(context, event_queue, message, metadata=None)`

Emit a durable chat-visible message.

### `load_context_state(context_id)` / `save_context_state(context_id, state)`

Load and persist agent-local state keyed by `contextId`.

### `get_provided_inputs(context)`

Extract structured follow-up answers from incoming A2A `DataPart`s.

### `send_input_required(context, event_queue, missing_inputs, hint, metadata=None)`

Emit a canonical final `INPUT_REQUIRED` payload.

## Streaming

To support `message/stream`, set this in `agent_card.json`:

```json
{
  "capabilities": {
    "streaming": true
  }
}
```

That is the only required configuration change. `_execute(...)` does not change.

Recommended:

- emit status updates for long-running steps
- emit chunked text artifacts when streaming incremental textual output
- return the final conversational result as the dict from `_execute(...)`

## `/api/chat` Compatibility Endpoint

`PrometheusAgent.run()` also exposes `POST /api/chat` as a convenience adapter for frontend and debug usage. It routes through the same execution path as A2A.

Accepted request shapes:

- `{"message": "plain text"}`
- `{"message": {...}}`
- `{"params": {...}}`

Optional fields:

- `task_id`
- `context_id`
- `conversation_id`
- `include_events`

Response fields:

- `ok`
- `task_id`
- `context_id`
- `state`
- `result`
- `events` when requested

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port to listen on | `8000` | No |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` | No |
| `AGENT_SECRET` | Shared secret for Bearer token authentication | - | Yes in production |
| `AGENT_SECRET_REQUIRED` | Enforce authentication | `true` | No |
| `REGISTRY_URL` | Registry service URL | - | No |
| `REDIS_URL` | Redis for artifact and context-state persistence | `redis://localhost:6379` | No |
| `AGENT_CONTEXT_TTL_SECONDS` | TTL for agent-local per-context state | `86400` | No |

## Project Structure

```text
my-agent/
├── agent.py
├── agent_card.json
├── .env
├── requirements.txt
└── Dockerfile
```

## Reference Example

See [`examples/agent_patterns.py`](../../examples/agent_patterns.py) for a single example agent that demonstrates:

- status updates
- durable conversation messages
- `INPUT_REQUIRED`
- per-`contextId` state persistence
- upstream data fetch patterns
- file and JSON artifact emission
