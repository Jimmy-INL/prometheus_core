# PrometheusAgent - Quick Start

## Installation

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```

## Minimal Agent Example

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        input_data = params.get("input_data")
        # Your logic here
        return {"status": "success", "data": input_data}

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port to listen on | `8000` | No |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` | No |
| `AGENT_SECRET` | Shared secret for authentication | - | Yes (production) |
| `AGENT_SECRET_REQUIRED` | Enforce authentication | `true` | No |
| `REGISTRY_URL` | Registry service URL | - | No |

## Required Files

### agent.py (your implementation)

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        # Your logic
        return {"status": "success"}

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

### agent_card.json (metadata)

```json
{
  "name": "My Agent",
  "description": "Agent description",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "my_skill",
      "name": "My Skill",
      "description": "Does XYZ",
      "inputSchema": {
        "type": "object",
        "properties": {
          "input_data": {"type": "string"}
        },
        "required": ["input_data"]
      }
    }
  ]
}
```

### .env (configuration)

```bash
AGENT_PORT=8000
AGENT_HOST=localhost
AGENT_SECRET=your-secret-here
REGISTRY_URL=http://registry:8000
```

## Enable Streaming

`PrometheusAgent` supports streaming without changing `_execute(params, context, event_queue)`.

Minimum requirement set this in `agent_card.json`:

```json
{
  "capabilities": {
    "streaming": true
  }
}
```

That is enough to accept `message/stream` requests.

Optional (recommended) for useful streaming:
- Emit intermediate status updates with `self.send_status_update(...)`
- Emit partial artifacts with `self.send_text_artifact(...)` or `self.send_json_artifact(...)`
- If your agent emits a terminal status (`final=True`) itself, the base executor will skip automatic terminal events to avoid duplicates

## Common Patterns

### Send Progress Updates

```python
from prometheus_api.agent import (
    PrometheusAgent,
    RequestContext,
    EventQueue,
)

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Working on request",
        )

        # Do work...

        return {"status": "success"}
```

### Use Storage Client

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue
from prometheus_api.storage_client import StorageClient, ConnectionConfig

class StorageAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = StorageClient(ConnectionConfig.from_env())

    async def _execute(self, params, context, event_queue):
        item = self.storage.items.get(params["item_id"])
        return {"status": "success", "item": item.name}
```

### Custom Port/Host

```python
agent = MyAgent(agent_name="My Agent")
agent.run(host="localhost", port=8001)
```

### Custom Agent Card Path

```python
agent = MyAgent(
    agent_name="My Agent",
    agent_card_path="/path/to/custom_agent_card.json"
)
```

## Project Structure

```
my-agent/
├── agent.py              # Your agent implementation
├── agent_card.json       # Agent metadata and skills
├── .env                  # Environment variables
├── requirements.txt      # Dependencies
└── Dockerfile            # Container config (optional)
```

## Testing Your Agent

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from your_agent import MyAgent
from prometheus_api.agent import RequestContext, EventQueue

@pytest.mark.asyncio
async def test_agent():
    agent = MyAgent(agent_name="Test")

    context = MagicMock(spec=RequestContext)
    context.task_id = "test-task"
    context.context_id = "test-context"

    event_queue = AsyncMock(spec=EventQueue)

    result = await agent._execute(
        {"input_data": "test"},
        context,
        event_queue,
    )

    assert result["status"] == "success"
```

## Run the Agent

```bash
# Set environment
export AGENT_PORT=8000
export AGENT_SECRET=my-secret

# Run
python agent.py
```

## Test with curl

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Send message (with auth)
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-secret" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{...}}'

# Stream events with SSE (requires capabilities.streaming=true)
curl -N -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-secret" \
  -d '{"jsonrpc":"2.0","method":"message/stream","id":"2","params":{...}}'
```

## Next Steps

- Read the full [Guide](GUIDE.md) for detailed documentation
- Check [ENV_SETUP.md](../ENV_SETUP.md) for environment configuration
- See `prometheus_agent_template/` for template examples
