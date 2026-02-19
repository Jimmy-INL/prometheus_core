# Agent Utilities

Utilities for building A2A (Agent-to-Agent) multi-agent systems.

## Quick Start

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

## Documentation

For complete documentation, see:

- **[PrometheusAgent Guide](../../docs/agent/GUIDE.md)** - Full API reference and examples
- **[Quick Start](../../docs/agent/QUICK_START.md)** - Minimal setup guide
- **[Environment Setup](../../docs/ENV_SETUP.md)** - Environment variables

## Components

- `PrometheusAgent` - Base class that handles all agent boilerplate
- `BearerTokenMiddleware` - Starlette middleware for shared secret authentication

## Installation

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```
