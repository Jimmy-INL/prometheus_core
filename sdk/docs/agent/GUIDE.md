# PrometheusAgent - Complete Guide

## Overview

`PrometheusAgent` is a base class that handles all the boilerplate for creating A2A-enabled agents. It provides:

- Automatic agent card loading from JSON
- Built-in Bearer token authentication
- Registry registration with authentication
- HTTP server setup with A2A protocol
- Parameter extraction and error handling
- Status update management

You just inherit from `PrometheusAgent`, override `_execute()`, and call `run()`.

## Quick Start

### Minimal Agent (15 lines)

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        input_data = params.get("input_data")

        # Your logic here
        result = {"status": "success", "data": input_data}

        return result

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

That's it! No need to:
- Manually load agent cards
- Set up authentication
- Create executors and request handlers
- Configure the HTTP server
- Register with the registry

## Usage

### Basic Agent

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue
from typing import Dict, Any

class DataProcessor(PrometheusAgent):
    """Agent that processes data."""

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Implement your agent's logic here."""

        # Extract parameters
        data = params.get("data")
        if not data:
            raise ValueError("data parameter is required")

        # Do your processing
        result = self.process_data(data)

        return {
            "status": "success",
            "result": result
        }

    def process_data(self, data):
        """Your custom processing logic."""
        # Implement your logic here
        return {"processed": data}

if __name__ == "__main__":
    agent = DataProcessor(agent_name="Data Processor")
    agent.run()
```

### With Progress Updates

```python
from prometheus_api.agent import (
    PrometheusAgent,
    RequestContext,
    EventQueue,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
import asyncio

class LongRunningAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        steps = ["Loading", "Processing", "Finalizing"]

        for i, step in enumerate(steps):
            # Send progress update using A2A event types
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    final=False,
                    status=TaskStatus(state=TaskState.working),
                )
            )

            # Do work
            await asyncio.sleep(1)

        return {"status": "success", "steps_completed": len(steps)}
```

### Using Storage Client

```python
from prometheus_api.agent import PrometheusAgent, RequestContext, EventQueue
from prometheus_api.storage_client import StorageClient, ConnectionConfig

class StorageAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize storage client
        self.storage = StorageClient(ConnectionConfig.from_env())

    async def _execute(self, params, context, event_queue):
        item_id = params.get("item_id")

        # Fetch from storage
        item = self.storage.items.get(item_id)

        return {
            "status": "success",
            "item": {
                "id": item.id,
                "name": item.name,
                "properties": item.properties
            }
        }
```

## API Reference

### PrometheusAgent

#### `__init__(agent_name, agent_card_path)`

**Parameters:**
- `agent_name` (str) - Name of the agent for logging and metadata
- `agent_card_path` (str, optional) - Path to agent_card.json (default: "./agent_card.json")

#### `_execute(params, context, event_queue)` [ABSTRACT]

**Must be overridden in subclass.**

**Parameters:**
- `params` (Dict[str, Any]) - Parameters extracted from A2A message
- `context` (RequestContext) - A2A request context with `task_id` and `context_id`
- `event_queue` (EventQueue) - Queue for sending status updates and artifacts

**Returns:**
- Dict[str, Any] - Analysis results

**Status Updates:**

You can send progress updates manually:
```python
await self.send_status_update(
    context=context,
    event_queue=event_queue,
    message="Working on request",
)
```

You can also stream partial artifacts:
```python
artifact_id = await self.send_text_artifact(
    context=context,
    event_queue=event_queue,
    name="progress",
    text='{"phase":"loading"}',
    last_chunk=False,
)

await self.send_text_artifact(
    context=context,
    event_queue=event_queue,
    name="progress",
    artifact_id=artifact_id,
    append=True,
    text='{"phase":"analyzing"}',
    last_chunk=True,
)
```

By default, you do not need to send terminal statuses:
- If your agent does **not** emit a final status, the base class sends final artifact + `completed` (or `failed` on exceptions).
- If your agent emits a final status (`final=True`) itself, the base class skips automatic terminal events to avoid duplicates.

#### `send_status_update(context, event_queue, state=TaskState.working, final=False, message=None, metadata=None)`

Helper for emitting task status events from your agent class.

**Parameters:**
- `context` (RequestContext) - Current request context
- `event_queue` (EventQueue) - Queue used to publish events
- `state` (TaskState, optional) - Status state (default: `TaskState.working`)
- `final` (bool, optional) - Whether this is a terminal status (default: `False`)
- `message` (str, optional) - Human-readable status text
- `metadata` (dict, optional) - Additional status metadata

#### `send_json_artifact(context, event_queue, payload, name="result", artifact_id=None, append=False, last_chunk=None, metadata=None)`

Helper for emitting JSON artifacts from your agent class.

**Parameters:**
- `context` (RequestContext) - Current request context
- `event_queue` (EventQueue) - Queue used to publish events
- `payload` (Any) - JSON-serializable payload
- `name` (str, optional) - Artifact name
- `artifact_id` (str, optional) - Artifact ID (reuse for chunk appends)
- `append` (bool, optional) - Append parts to existing artifact
- `last_chunk` (bool, optional) - Mark last chunk in stream
- `metadata` (dict, optional) - Artifact metadata

**Returns:**
- `str` - `artifact_id` used for the event

#### `send_text_artifact(context, event_queue, text, name="result", artifact_id=None, append=False, last_chunk=None, metadata=None)`

Helper for emitting text artifacts from your agent class.

**Parameters:**
- `context` (RequestContext) - Current request context
- `event_queue` (EventQueue) - Queue used to publish events
- `text` (str) - Text content
- `name` (str, optional) - Artifact name
- `artifact_id` (str, optional) - Artifact ID (reuse for chunk appends)
- `append` (bool, optional) - Append parts to existing artifact
- `last_chunk` (bool, optional) - Mark last chunk in stream
- `metadata` (dict, optional) - Artifact metadata

**Returns:**
- `str` - `artifact_id` used for the event

#### `run(host, port)`

Start the agent server.

**Parameters:**
- `host` (str, optional) - Host to bind to (default: "0.0.0.0")
- `port` (int, optional) - Port to listen on (default: from AGENT_PORT env var or 8000)

**Usage:**
```python
agent.run()                    # Use env vars
agent.run(port=8001)          # Override port
agent.run(host="localhost")   # Local only
```

#### Streaming Capability

To make an agent streaming-capable, set this in `agent_card.json`:

```json
{
  "capabilities": {
    "streaming": true
  }
}
```

That is the only required change to enable `message/stream`.

Notes:
- `_execute` signature stays the same: `async def _execute(self, params, context, event_queue)`.
- Returning a normal final dict still works for both `message/send` and `message/stream`.
- For useful live progress, emit intermediate status/artifact events from `_execute`.

#### `load_agent_card()` [Advanced]

Load agent card from JSON file. Called automatically by `run()`.

**Returns:**
- Dict[str, Any] - Agent card with URL updated from environment

#### `register_with_registry(agent_card)` [Advanced]

Register agent with registry service. Called automatically by `run()`.

**Parameters:**
- `agent_card` (Dict[str, Any]) - Agent card to register

#### `create_executor()` [Advanced]

Create the executor instance. Override if you need custom executor behavior.

**Returns:**
- PrometheusAgentExecutor - Executor instance

### PrometheusAgentExecutor (Advanced / Custom Executors)

If you subclass `PrometheusAgentExecutor` directly, additional protected helpers are available:
- `_emit_status(...)`
- `_emit_json_artifact(...)`
- `_emit_text_artifact(...)`

These are executor-level internals. For normal `PrometheusAgent` subclasses, prefer:
- `send_status_update(...)`
- `send_json_artifact(...)`
- `send_text_artifact(...)`

## Environment Variables

The base class reads these environment variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port to listen on | `8000` | No |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` | No |
| `AGENT_SECRET` | Shared secret for authentication | - | Yes (production) |
| `AGENT_SECRET_REQUIRED` | Enforce authentication | `true` | No |
| `REGISTRY_URL` | Registry service URL | - | No |

## Project Structure

Your agent project should have:

```
my-agent/
├── agent.py              # Your agent implementation
├── agent_card.json       # Agent metadata and skills
├── .env.example          # Environment template
├── requirements.txt      # Dependencies
└── Dockerfile            # Container config (optional)
```

**agent_card.json:**
```json
{
  "name": "My Agent",
  "description": "Does something useful",
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

## What the Base Class Handles

### Automatic Boilerplate

1. **Agent Card Loading**
   - Loads from `agent_card.json`
   - Updates URL from environment variables
   - Validates JSON format

2. **HTTP Server Setup**
   - Creates A2A Starlette application
   - Sets up request handler
   - Configures task store
   - Starts uvicorn server

3. **Authentication**
   - Adds Bearer token middleware
   - Reads AGENT_SECRET from environment
   - Handles authentication disabled mode

4. **Registry Registration**
   - Registers agent with registry service
   - Includes Bearer token in request
   - Continues gracefully if registry unavailable

5. **Parameter Extraction**
   - Parses JSON from A2A message
   - Validates message format
   - Logs parameters

6. **Status Management**
   - Sends "working" status automatically
   - Sends final artifact and "completed" status when agent does not self-finalize
   - Sends "failed" status on error when agent does not self-finalize
   - Avoids duplicate terminal events when agent emits final status itself

7. **Error Handling**
   - Catches and logs exceptions
   - Sends error status to client
   - Re-raises for proper error propagation

## Advanced Usage

### Custom Initialization

```python
class MyAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initialize custom resources
        self.storage = StorageClient(ConnectionConfig.from_env())
        self.cache = {}

    async def _execute(self, params, context, event_queue):
        # Use self.storage, self.cache, etc.
        pass
```

### Custom Agent Card Path

```python
agent = MyAgent(
    agent_name="My Agent",
    agent_card_path="/path/to/custom_agent_card.json"
)
agent.run()
```

### Custom Port/Host

```python
agent = MyAgent(agent_name="My Agent")
agent.run(host="localhost", port=8001)
```

### Override Executor Creation

```python
class MyAgent(PrometheusAgent):
    def create_executor(self):
        # Create custom executor if needed
        executor = super().create_executor()
        # Customize executor
        return executor
```

### Override Registry Registration

```python
class MyAgent(PrometheusAgent):
    def register_with_registry(self, agent_card):
        # Custom registration logic
        super().register_with_registry(agent_card)
        # Additional registration steps
```

## Comparison: Before vs After

### Before (330 lines)

```python
import os, sys, json, logging
from typing import Dict, Any
from datetime import datetime
from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from prometheus_api.agent.middleware import BearerTokenMiddleware
import uvicorn

# ... lots of boilerplate code ...

class MyExecutor(AgentExecutor):
    async def execute(self, context, event_queue):
        # ... manual parameter extraction ...
        # ... manual status updates ...
        # ... manual error handling ...
        pass

def main():
    # ... 50+ lines of server setup ...
    pass

if __name__ == "__main__":
    main()
```

### After (15 lines - 95% reduction!)

```python
from prometheus_api.agent import PrometheusAgent

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        # Your logic here
        return {"status": "success"}

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

## Benefits

### 1. Simplicity
- **Before:** 330 lines of boilerplate
- **After:** 15-20 lines of agent logic

### 2. Consistency
- All agents use the same authentication setup
- Same error handling patterns
- Unified logging format

### 3. Maintainability
- Fix bugs in one place (base class)
- All agents benefit from improvements
- Easy to add new features

### 4. Less Error-Prone
- No forgetting to add authentication
- No mistakes in server setup
- Consistent parameter extraction

### 5. Focus on Logic
- Users focus on `_execute()`
- No need to understand A2A internals
- No need to manage HTTP server details

## What You Still Control

You have full control over:
- Agent logic in `_execute()`
- Custom initialization in `__init__()`
- Agent card JSON file
- Input schema and validation
- Progress updates via event_queue
- Error handling in your logic

## Requirements

Install with the `[agent]` extra:

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```

This includes:
- `a2a-sdk[http-server]` - A2A protocol implementation
- `starlette` - Web framework
- `uvicorn` - ASGI server
- `httpx` - HTTP client (for registry registration)

## Testing

Test your agent:

```python
# test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from your_agent import MyAgent
from prometheus_api.agent import RequestContext, EventQueue

@pytest.mark.asyncio
async def test_agent_logic():
    agent = MyAgent(agent_name="Test Agent")

    # Mock context and event queue
    context = MagicMock(spec=RequestContext)
    context.task_id = "test-task"
    context.context_id = "test-context"

    event_queue = AsyncMock(spec=EventQueue)

    # Test _execute directly
    result = await agent._execute(
        {"input_data": "test"},
        context,
        event_queue,
    )

    assert result["status"] == "success"
```

## Logging

The base class logs:
- Agent initialization
- Agent card loading
- Authentication status
- Registry registration
- Execution start/complete
- Errors (with stack traces)

Configure logging in your agent:
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Error Handling

The base class automatically:
- Catches exceptions in `_execute()`
- Logs errors with stack traces
- Sends "failed" status to client
- Re-raises exception for proper error propagation

You just need to raise exceptions in your code:
```python
async def _execute(self, params, context, event_queue):
    if "required_param" not in params:
        raise ValueError("required_param is required")

    # Process...
    return result
```

## Migration from Old Template

### Before
```python
class MyExecutor(AgentExecutor):
    def execute(self, context, event_queue):
        params = self._extract_params(context)
        result = self._execute(params, event_queue)
        return result

    def _execute(self, params, event_queue):
        # Your logic
        return result

def main():
    agent_card = create_agent_card()
    executor = MyExecutor()
    # ... lots of boilerplate ...

if __name__ == "__main__":
    main()
```

### After
```python
class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        # Same logic (now async)
        return result

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

**Delete:** All helper functions (`create_agent_card`, `register_with_registry`, `main`)
**Keep:** Just `_execute()` logic (make it async)
**Add:** Single line to create and run agent

## Next Steps

- See the [Quick Start Guide](QUICK_START.md) for a condensed reference
- Check [ENV_SETUP.md](../ENV_SETUP.md) for environment configuration
- See `prometheus_agent_template/` for template examples
