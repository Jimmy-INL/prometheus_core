# PrometheusAgent - Complete Guide

## Overview

`PrometheusAgent` is a base class that handles all the boilerplate for creating A2A-enabled agents. It provides:

- Automatic agent card loading from JSON
- Built-in Bearer token authentication
- Registry registration with authentication
- HTTP server setup with A2A protocol
- Parameter extraction and error handling
- Status update management

You just inherit from `PrometheusAgent`, override `process_analysis()`, and call `run()`.

## Quick Start

### Minimal Agent (15 lines)

```python
from prometheus_api.agent import PrometheusAgent

class MyAgent(PrometheusAgent):
    def process_analysis(self, params, event_queue):
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
from prometheus_api.agent import PrometheusAgent
from typing import Dict, Any

class DataProcessor(PrometheusAgent):
    """Agent that processes data."""

    def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
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
class LongRunningAgent(PrometheusAgent):
    def process_analysis(self, params, event_queue):
        import time

        steps = ["Loading", "Processing", "Finalizing"]

        for i, step in enumerate(steps):
            # Send progress update
            progress = (i + 1) / len(steps) * 100
            event_queue.put({
                "type": "status",
                "status": "working",
                "message": f"{step}... ({progress:.0f}% complete)"
            })

            # Do work
            time.sleep(1)

            # Send intermediate result
            event_queue.put({
                "type": "artifact",
                "data": json.dumps({"step": step, "progress": progress})
            })

        return {"status": "success", "steps_completed": len(steps)}
```

### Using Storage Client

```python
from prometheus_api.agent import PrometheusAgent
from prometheus_api.storage_client import StorageClient, ConnectionConfig

class StorageAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize storage client
        self.storage = StorageClient(ConnectionConfig.from_env())

    def process_analysis(self, params, event_queue):
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

#### `process_analysis(params, event_queue)` [ABSTRACT]

**Must be overridden in subclass.**

**Parameters:**
- `params` (Dict[str, Any]) - Parameters extracted from A2A message
- `event_queue` (Queue) - Queue for sending status updates and artifacts

**Returns:**
- Dict[str, Any] - Analysis results

**Status Updates:**

Send via event_queue:
```python
# Working status
event_queue.put({
    "type": "status",
    "status": "working",
    "message": "Processing..."
})

# Artifact (intermediate result)
event_queue.put({
    "type": "artifact",
    "data": json.dumps({"result": "..."})
})
```

Note: You don't need to send "completed" or "failed" status - the base class handles that automatically.

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
   - Sends "completed" status on success
   - Sends "failed" status on error
   - Sends result as artifact

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

    def process_analysis(self, params, event_queue):
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

logging.basicConfig(...)
logger = logging.getLogger(__name__)

class MyExecutor(AgentExecutor):
    def __init__(self):
        super().__init__()
        logger.info("Initialized")

    def execute(self, context, event_queue):
        try:
            logger.info("Starting execution")
            params = self._extract_params(context)
            event_queue.put({"type": "status", "status": "working", ...})
            result = self.process_analysis(params, event_queue)
            event_queue.put({"type": "status", "status": "completed", ...})
            event_queue.put({"type": "artifact", ...})
            return result
        except Exception as e:
            logger.error(...)
            event_queue.put({"type": "status", "status": "failed", ...})
            raise

    def _extract_params(self, context):
        message = context.get("message", {})
        parts = message.get("parts", [])
        if not parts:
            raise ValueError(...)
        text = parts[0].get("text", "{}")
        try:
            params = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(...)
        return params

    def process_analysis(self, params, event_queue):
        # Your logic here
        return {"status": "success"}

def create_agent_card():
    agent_card_path = os.path.join(os.path.dirname(__file__), "agent_card.json")
    with open(agent_card_path, 'r') as f:
        agent_card = json.load(f)
    port = os.getenv('AGENT_PORT', '8000')
    host = os.getenv('AGENT_HOST', 'localhost')
    agent_card['url'] = f"http://{host}:{port}"
    return agent_card

def register_with_registry(agent_card):
    import httpx
    registry_url = os.getenv("REGISTRY_URL", "http://registry:8000")
    agent_secret = os.getenv("AGENT_SECRET")
    headers = {}
    if agent_secret:
        headers["Authorization"] = f"Bearer {agent_secret}"
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            response = client.post(f"{registry_url}/agents/register", json=agent_card)
            response.raise_for_status()
    except Exception as e:
        logger.error(...)

def main():
    agent_card = create_agent_card()
    executor = MyExecutor()
    request_handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    builder = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    app = builder.build()
    agent_secret = os.getenv("AGENT_SECRET")
    agent_secret_required = os.getenv("AGENT_SECRET_REQUIRED", "true").lower() in ["true", "1", "yes"]
    if agent_secret or agent_secret_required:
        app.add_middleware(BearerTokenMiddleware, secret=agent_secret, required=agent_secret_required)
    register_with_registry(agent_card)
    port = int(os.getenv("AGENT_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
```

### After (15 lines - 95% reduction!)

```python
from prometheus_api.agent import PrometheusAgent

class MyAgent(PrometheusAgent):
    def process_analysis(self, params, event_queue):
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
- Users focus on `process_analysis()`
- No need to understand A2A internals
- No need to manage HTTP server details

## What You Still Control

You have full control over:
- Agent logic in `process_analysis()`
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
from your_agent import MyAgent

def test_agent_logic():
    agent = MyAgent(agent_name="Test Agent")

    # Mock event queue
    events = []
    class MockQueue:
        def put(self, event):
            events.append(event)

    # Test process_analysis directly
    result = agent.process_analysis(
        {"input_data": "test"},
        MockQueue()
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
- Catches exceptions in `process_analysis()`
- Logs errors with stack traces
- Sends "failed" status to client
- Re-raises exception for proper error propagation

You just need to raise exceptions in your code:
```python
def process_analysis(self, params, event_queue):
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
        result = self.process_analysis(params, event_queue)
        return result

    def process_analysis(self, params, event_queue):
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
    def process_analysis(self, params, event_queue):
        # Same logic
        return result

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

**Delete:** All helper functions (`create_agent_card`, `register_with_registry`, `main`)
**Keep:** Just `process_analysis()` logic
**Add:** Single line to create and run agent

## Next Steps

- See the [Quick Start Guide](QUICK_START.md) for a condensed reference
- Check [ENV_SETUP.md](../ENV_SETUP.md) for environment configuration
- See `prometheus_agent_template/` for template examples
