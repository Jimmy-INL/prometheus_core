# Agent Utilities

Utilities for building A2A multi-agent systems with `PrometheusAgent`.

## Core Contract

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

The base class handles:

- agent-card loading
- auth middleware
- registry registration
- A2A request handling
- final status emission from your returned dict

Use helper methods when needed:

- `send_status_update(...)` for transient progress
- `send_artifact_reference(...)` for URI-backed file artifacts
- `send_json_artifact(..., catalog_artifact=True)` for reusable inline JSON artifacts
- `send_conversation_message(...)` for durable chat-visible messages
- `send_input_required(...)` for missing-input requests
- `load_context_state(...)` / `save_context_state(...)` for resumable agent-local state keyed by `contextId`

To enable streaming (`message/stream`), set `"capabilities": {"streaming": true}` in `agent_card.json`.

## Documentation

- **[PrometheusAgent Guide](../../docs/agent/GUIDE.md)**: full API reference, patterns, and examples
- **[Quick Start](../../docs/agent/QUICK_START.md)**: minimal setup plus common agent actions
- **[Environment Setup](../../docs/ENV_SETUP.md)**: environment variables
- **[Reference Example](../../examples/agent_patterns.py)**: one example agent showing status, artifacts, input requests, and stateful resume

## Components

- `PrometheusAgent`: base class for A2A-enabled specialists
- `MissingInput`: canonical descriptor for `INPUT_REQUIRED`
- `ArtifactReference` / `ArtifactRegistry`: conversation artifact helpers
- `ContextStateStore`: per-agent state persistence keyed by `contextId`
- `BearerTokenMiddleware`: shared-secret auth middleware

## Installation

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```
