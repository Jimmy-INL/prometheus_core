# Prometheus API

A Python toolkit for building data-driven applications with storage operations and A2A-enabled agents.

## Components

| Component | Description | Documentation |
|-----------|-------------|---------------|
| **StorageClient** | Full-featured client for storage operations with sync/async APIs | [Guide](docs/storage-client/GUIDE.md) \| [Quick Start](docs/storage-client/QUICK_START.md) |
| **PrometheusAgent** | Base class for building A2A-enabled agents with minimal boilerplate | [Guide](docs/agent/GUIDE.md) \| [Quick Start](docs/agent/QUICK_START.md) |

## Installation

See [INSTALL.md](INSTALL.md) for full options. Quick paths:

- **Runtime:** `docker pull mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest`
- **As a library:** `pip install git+https://github.inl.gov/genesis/prometheus_api.git`
- **For development:** `git clone … && cd prometheus_api && uv sync` (then `make check`, `make test`)

## Quick Start - StorageClient

```python
from prometheus_api.storage_client import StorageClient, ConnectionConfig, ItemCreate

# Configure from environment variables
config = ConnectionConfig.from_env()

with StorageClient(config) as client:
    # Create an item
    item = client.items.create(ItemCreate(
        name="My Item",
        properties={"key": "value"},
        tags=["example"]
    ))

    # Upload a file
    file_meta = client.files.upload(Path("data.csv"))

    # Search
    results = client.search.by_tags(["example"])
```

**[Full StorageClient Guide](docs/storage-client/GUIDE.md)** | **[Quick Reference](docs/storage-client/QUICK_START.md)**

## Quick Start - PrometheusAgent

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

**[Full PrometheusAgent Guide](docs/agent/GUIDE.md)** | **[Quick Reference](docs/agent/QUICK_START.md)**

## Environment Variables

### StorageClient

| Variable | Description | Required |
|----------|-------------|----------|
| `DEEPLYNX_KEY` | API key | Yes* |
| `DEEPLYNX_SECRET` | API secret | Yes* |
| `DEEPLYNX_ORG_ID` | Organization ID | Yes |
| `DEEPLYNX_PROJECT_ID` | Project ID | Yes |
| `DEEPLYNX_BASE_URL` | Custom API URL | No |

*Or use `DEEPLYNX_JWT_TOKEN` instead

### PrometheusAgent

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_PORT` | Port to listen on | `8000` |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` |
| `AGENT_SECRET` | Shared secret for auth | - |
| `REGISTRY_URL` | Registry service URL | - |

**[Full Environment Setup Guide](docs/ENV_SETUP.md)**

## Documentation

| Document | Description |
|----------|-------------|
| [StorageClient Guide](docs/storage-client/GUIDE.md) | Complete StorageClient API reference |
| [StorageClient Quick Start](docs/storage-client/QUICK_START.md) | Condensed reference and examples |
| [PrometheusAgent Guide](docs/agent/GUIDE.md) | Complete PrometheusAgent documentation |
| [PrometheusAgent Quick Start](docs/agent/QUICK_START.md) | Minimal agent setup guide |
| [Environment Setup](docs/ENV_SETUP.md) | Environment variables for both components |
| [Testing Guide](docs/TESTING.md) | Running and writing tests |
| [Installation Guide](INSTALL.md) | Detailed installation options |
| [Development Guide](DEVELOPMENT.md) | Architecture, commands, and conventions |
| [HPC Notes](docs/hpc.md) | INL HPC: podman + CA bundle, SSL workarounds |

## Features

### StorageClient
- CRUD operations for items
- File upload/download (including chunked uploads)
- Relationship management
- Search and query capabilities
- Timeseries data support
- Bulk operations
- Automatic pagination
- Sync and async APIs
- Type safety with Pydantic

### PrometheusAgent
- Automatic agent card loading
- Built-in Bearer token authentication
- Registry registration
- HTTP server setup with A2A protocol
- Optional `message/stream` support (`agent_card.capabilities.streaming=true`)
- Final response emission from the returned `_execute(...)` dict
- Status updates, native artifacts, and `INPUT_REQUIRED` helpers
- Per-agent context-state persistence keyed by `contextId`
- 95% reduction in boilerplate code

## Examples

See the `examples/` directory for working code:
- `basic_usage.py` - StorageClient CRUD operations
- `async_usage.py` - Async/await patterns
- `file_operations.py` - File upload/download
- `bulk_operations.py` - Bulk operations
- `agent_patterns.py` - PrometheusAgent status, artifacts, input requests, and stateful resume
- `env_config_usage.py` - Loading `ConnectionConfig` from `.env`
- `list_datasources.py` - Print available DeepLynx data source IDs for your project

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) and [INSTALL.md](INSTALL.md#development) for setup. The common loop is:

```bash
make check    # ruff + mypy
make test     # pytest (unit only)
make fix      # auto-fix lint and format
```

## License

MIT License

## Support

For issues and questions, please contact your system administrator or open an issue in the repository.
