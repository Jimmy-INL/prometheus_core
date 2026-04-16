# PrometheusAgent Quick Start

Subclass `PrometheusAgent`, implement `_execute`, return a dict. The base class handles everything else.

## Install

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```

## Minimal agent

```python
from prometheus_api.agent import EventQueue, PrometheusAgent, RequestContext


class MyAgent(PrometheusAgent):
    async def _execute(self, params, context: RequestContext, event_queue: EventQueue) -> dict:
        return {
            "message": f"Received skill={params.get('skill_id')!r}.",
            "agent": self.agent_name,
        }


if __name__ == "__main__":
    MyAgent(agent_name="My Agent").run()
```

## Minimal `agent_card.json`

```json
{
  "name": "My Agent",
  "description": "One-sentence description for orchestrator routing.",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": { "streaming": true, "pushNotifications": false },
  "skills": [
    {
      "id": "do_analysis",
      "name": "Do Analysis",
      "description": "Runs an analysis. Requests any missing parameters interactively.",
      "usage_notes": "Use when the user asks for analysis, lookup, or evaluation.",
      "tags": ["analysis"],
      "inputSchema": {
        "type": "object",
        "properties": {
          "material_id": { "type": "string", "description": "Material identifier" }
        },
        "required": ["material_id"]
      }
    }
  ]
}
```

## Status updates

```python
await self.send_status_update(context, event_queue, message="Loading data…")
await self.send_status_update(context, event_queue, message="Running model…")
# base class emits final "completed" status from your return dict — don't emit it manually
```

## JSON artifact

```python
await self.send_json_artifact(
    context=context, event_queue=event_queue,
    payload={"score": 0.95, "status": "acceptable"},
    name="result",
    description="Analysis result",
    json_type="prometheus.my_agent.result.v1",
    catalog_artifact=True,    # registers for downstream reuse
)
return {"message": "Analysis complete.", "agent": self.agent_name}
```

## File artifact

```python
artifact = await self.send_artifact_reference(
    context=context, event_queue=event_queue,
    name="report.pdf",
    description="Generated report",
    uri="file:///tmp/report.pdf",
    mime_type="application/pdf",
)
return {"message": "Report ready.", "agent": self.agent_name}
```

## DeepLynx artifact

Upload a local file to DeepLynx, attach metadata, and emit a `deeplynx://` URI reference.

```python
from pathlib import Path
from prometheus_api.storage_client.connection import ConnectionConfig

config = ConnectionConfig.from_env()   # reads DEEPLYNX_KEY / DEEPLYNX_SECRET / etc.

artifact = await self.send_deeplynx_artifact(
    context=context, event_queue=event_queue,
    file_path=Path("/tmp/results.csv"),
    name="results.csv",
    description="Simulation output",
    storage_config=config,
    mime_type="text/csv",
    json_type="prometheus.my_agent.results.v1",   # optional semantic tag
    tags=["simulation", "validated"],
    metadata={"run_id": "abc123"},
)
# artifact.uri  → "deeplynx://organizations/1/projects/2/items/42"
# artifact.metadata["deeplynx_item_id"]  → 42
# artifact.metadata["deeplynx_file_id"]  → 99
return {"message": "Results uploaded.", "agent": self.agent_name}
```

The DeepLynx item's `properties` store `mime_type`, `json_type`, `file_id`, and any
extra `metadata` keys, so the artifact is queryable in DeepLynx independently of
the Prometheus catalog.

## `INPUT_REQUIRED` — requesting user input

Save state **before** calling `send_input_required`, then **always** `return {}`.

```python
from prometheus_api.agent import MissingInput


async def _execute(self, params, context, event_queue):
    context_id = str(context.context_id)
    state = self.load_context_state(context_id)
    resolved = {**state.get("resolved", {}), **self.get_provided_inputs(context)}

    if "temperature_c" not in resolved:
        self.save_context_state(context_id, {"resolved": resolved})   # save BEFORE
        await self.send_input_required(
            context=context, event_queue=event_queue,
            missing_inputs=[
                MissingInput(
                    name="temperature_c",
                    description="Operating temperature in °C.",
                    user_prompt="What operating temperature (°C)?",
                    type="number",
                    required=True,
                )
            ],
            hint="I need an operating temperature to continue.",
        )
        return {}   # ← required — task is suspended

    self.save_context_state(context_id, {})   # clear on completion
    return {"message": f"Running at {resolved['temperature_c']} °C.", "agent": self.agent_name}
```

Key rules:
- Use `context.context_id` as the state key (not `task_id` — it changes each turn)
- `get_provided_inputs()` returns `{}` on the first turn; values appear on resume
- Bundle all missing fields into **one** `send_input_required` call — the form renders them as separate widgets
- `type="boolean"` renders as a checkbox; `options=[...]` renders as a dropdown

## Multiple skills

```python
async def _execute(self, params, context, event_queue):
    skill_id = params.get("skill_id")
    dispatch = {
        "analyze": self._handle_analyze,
        "list":    self._handle_list,
    }
    handler = dispatch.get(skill_id)
    if handler is None:
        raise ValueError(f"Unknown skill: {skill_id!r}")
    return await handler(params, context, event_queue)
```

## Sync code in async context

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_POOL = ThreadPoolExecutor(max_workers=4)

async def _execute(self, params, context, event_queue):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_POOL, self._sync_computation, params)
    return {"result": result}

def _sync_computation(self, params):
    return heavy_library_call(params)
```

## `.env`

```env
AGENT_PORT=8001
AGENT_HOST=host.docker.internal
AGENT_SECRET=my-secret
LITELLM_URL=http://litellm:4000
LITELLM_MASTER_KEY=sk-...
```

## Next steps

- [PrometheusAgent Guide](./GUIDE.md) — full reference with pitfalls, multi-round forms, lifecycle hooks
- [`examples/agent_patterns.py`](../../examples/agent_patterns.py) — runnable reference agent
- [Environment Setup](../ENV_SETUP.md)
