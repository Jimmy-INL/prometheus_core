# Agent Utilities

Utilities for building A2A (Agent-to-Agent) multi-agent systems.

## Overview

This module provides reusable components for building agents that communicate using the Agent-to-Agent (A2A) protocol.

**Quick Start:**
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

That's all you need! The base class handles authentication, registry, and server setup.

## Components

### PrometheusAgent (Base Class)

**NEW!** Base class that handles all agent boilerplate.

**Features:**
- Automatic agent card loading from JSON
- Built-in Bearer token authentication
- Registry registration with auth
- HTTP server setup with A2A protocol
- Parameter extraction and error handling
- Status update management

**Usage:**
1. Inherit from `PrometheusAgent`
2. Override `process_analysis()` method
3. Call `run()`

**See:** [BASE_CLASS.md](./BASE_CLASS.md) for complete documentation and examples.

### BearerTokenMiddleware

Starlette middleware for shared secret authentication using Bearer tokens.

**Features:**
- Validates `Authorization: Bearer <token>` headers on incoming requests
- Configurable via `AGENT_SECRET` environment variable
- Exempts health check and agent card endpoints
- Returns JSON-RPC 2.0 formatted errors on authentication failure
- Never logs full token values (security best practice)

**Usage:**

```python
from a2a.server.apps import A2AStarletteApplication
from prometheus_api.agent.middleware import BearerTokenMiddleware
import uvicorn
import os

# Build A2A application
builder = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
app = builder.build()

# Add Bearer token authentication
app.add_middleware(
    BearerTokenMiddleware,
    secret=os.getenv("AGENT_SECRET"),
    required=True
)

# Start server
uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Environment Variables:**
- `AGENT_SECRET`: The shared secret for authentication
- `AGENT_SECRET_REQUIRED`: Whether to enforce authentication (default: true)

**Configuration:**

```python
# Require authentication
app.add_middleware(BearerTokenMiddleware, secret="my-secret", required=True)

# Optional authentication (accepts requests with or without token)
app.add_middleware(BearerTokenMiddleware, secret="my-secret", required=False)

# Read from environment
app.add_middleware(BearerTokenMiddleware)  # Uses AGENT_SECRET env var
```

**Security Notes:**
- All agents in a deployment should share the same secret
- Use cryptographically random secrets (32+ characters)
- Never commit secrets to version control
- Consider using TLS/HTTPS in production
- Health check (`/health`) and agent card (`/.well-known/agent.json`) are exempt

## Installation

This module is part of the `prometheus-api` package and requires the `[agent]` extra:

```bash
# Install from git
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"

# Or in requirements.txt
git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]
```

## Requirements

- Python >= 3.8
- starlette >= 0.27.0

## Example

Complete example of an A2A agent with authentication:

```python
import os
from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from prometheus_api.agent.middleware import BearerTokenMiddleware
import uvicorn

class MyExecutor(AgentExecutor):
    def execute(self, context, event_queue):
        return {"status": "success"}

# Create components
executor = MyExecutor()
handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
agent_card = {...}  # Your agent card

# Build application
builder = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
app = builder.build()

# Add authentication
app.add_middleware(BearerTokenMiddleware, secret=os.getenv("AGENT_SECRET"), required=True)

# Start server
uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Testing

To test authentication:

```bash
# Without token (should fail)
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{...}}'

# With valid token (should succeed)
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret" \
  -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{...}}'

# Health check (no auth required)
curl http://localhost:8000/health
```

## Related

- `prometheus_api.storage_client`: Storage backend abstraction for data persistence
- A2A SDK: Agent-to-Agent protocol implementation
