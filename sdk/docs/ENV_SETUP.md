# Environment Variable Setup Guide

This guide covers environment configuration for both the StorageClient and PrometheusAgent components.

## Quick Setup

1. **Copy the template:**
```bash
cp .env.example .env
```

2. **Edit `.env` with your values:**
```bash
vim .env
# or
nano .env
```

3. **Use in your code:**
```python
# StorageClient
from prometheus_api.storage_client import ConnectionConfig, StorageClient
config = ConnectionConfig.from_env()

# PrometheusAgent
from prometheus_api.agent import PrometheusAgent
# Reads env vars automatically via run()
```

---

## Agent Configuration

Environment variables for `PrometheusAgent`:

### Agent Server

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port to listen on | `8000` | No |
| `AGENT_HOST` | Hostname for agent card URL | `localhost` | No |

### Agent Authentication

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_SECRET` | Shared secret for Bearer token auth | - | Yes (production) |
| `AGENT_SECRET_REQUIRED` | Enforce authentication | `true` | No |

### Agent Registry

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REGISTRY_URL` | Registry service URL for auto-registration | - | No |

### Example Agent .env

```bash
# Agent Server
AGENT_PORT=8000
AGENT_HOST=localhost

# Authentication
AGENT_SECRET=your-shared-secret-here
AGENT_SECRET_REQUIRED=true

# Registry (optional)
REGISTRY_URL=http://registry:8000
```

### Agent Usage

```python
from prometheus_api.agent import PrometheusAgent

class MyAgent(PrometheusAgent):
    def process_analysis(self, params, event_queue):
        return {"status": "success"}

if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()  # Reads AGENT_* env vars automatically
```

---

## StorageClient Configuration

Environment variables for `StorageClient`:

### Authentication (choose one method)

**Option 1: API Key/Secret (Recommended)**
```bash
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret
```

**Option 2: JWT Token**
```bash
DEEPLYNX_JWT_TOKEN=your-jwt-token
```

### Organization & Project

```bash
DEEPLYNX_ORG_ID=123          # Your organization ID (integer)
DEEPLYNX_PROJECT_ID=456      # Your project ID (integer)
```

### Optional Settings

```bash
# Custom API endpoint (defaults to INL DeepLynx)
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1

# Connection settings
DEEPLYNX_TIMEOUT=30.0        # Request timeout in seconds
DEEPLYNX_MAX_RETRIES=3       # Number of retry attempts
DEEPLYNX_VERIFY_SSL=true     # SSL certificate verification
```

### Example StorageClient .env

```bash
# Authentication
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret

# Organization & Project
DEEPLYNX_ORG_ID=123
DEEPLYNX_PROJECT_ID=456

# Optional
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1
DEEPLYNX_TIMEOUT=30.0
```

### StorageClient Usage

```python
from prometheus_api.storage_client import ConnectionConfig, StorageClient

# Load from .env file
config = ConnectionConfig.from_env()

with StorageClient(config) as client:
    items = client.items.list()
```

---

## Combined Configuration

If using both StorageClient and PrometheusAgent, combine variables in one `.env`:

```bash
# ===== Agent Configuration =====
AGENT_PORT=8000
AGENT_HOST=localhost
AGENT_SECRET=your-shared-secret-here
AGENT_SECRET_REQUIRED=true
REGISTRY_URL=http://registry:8000

# ===== StorageClient Configuration =====
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret
DEEPLYNX_ORG_ID=123
DEEPLYNX_PROJECT_ID=456
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1
```

### Combined Usage

```python
from prometheus_api.agent import PrometheusAgent
from prometheus_api.storage_client import StorageClient, ConnectionConfig

class StorageAgent(PrometheusAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # StorageClient reads DEEPLYNX_* vars
        self.storage = StorageClient(ConnectionConfig.from_env())

    def process_analysis(self, params, event_queue):
        item = self.storage.items.get(params["item_id"])
        return {"status": "success", "item": item.name}

if __name__ == "__main__":
    # PrometheusAgent reads AGENT_* vars
    agent = StorageAgent(agent_name="Storage Agent")
    agent.run()
```

---

## Usage Patterns

### Load from Default .env File

```python
from prometheus_api.storage_client import ConnectionConfig

# Loads from .env in current directory
config = ConnectionConfig.from_env()
```

### Load from Specific File

```python
from pathlib import Path

# Load from a specific location
config = ConnectionConfig.from_env(
    env_file=Path("/path/to/production.env")
)
```

### Override Specific Values

```python
# Load from .env but override org/project
config = ConnectionConfig.from_env(
    organization_id=999,  # Override env var
    project_id=888,       # Override env var
    timeout=60.0          # Custom timeout
)
```

### Multiple Environments

**Development (.env.dev):**
```bash
DEEPLYNX_KEY=dev-key
DEEPLYNX_SECRET=dev-secret
DEEPLYNX_ORG_ID=100
DEEPLYNX_PROJECT_ID=200
DEEPLYNX_BASE_URL=https://dev.deeplynx.com/api/v1
```

**Production (.env.prod):**
```bash
DEEPLYNX_KEY=prod-key
DEEPLYNX_SECRET=prod-secret
DEEPLYNX_ORG_ID=500
DEEPLYNX_PROJECT_ID=600
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1
```

**Load based on environment:**
```python
import os
from pathlib import Path

env = os.getenv("APP_ENV", "dev")
env_file = Path(f".env.{env}")

config = ConnectionConfig.from_env(env_file=env_file)
```

---

## Security Best Practices

### DO

1. **Use `.env` files for local development**
```bash
# .env is gitignored by default
cp .env.example .env
# Edit with your credentials
```

2. **Use environment variables in production**
```bash
# Set in your deployment system
export DEEPLYNX_KEY=prod-key
export AGENT_SECRET=prod-secret
```

3. **Keep `.env.example` updated**
```bash
# Template without actual credentials
DEEPLYNX_KEY=your-api-key-here
AGENT_SECRET=your-secret-here
```

4. **Use different credentials per environment**

### DON'T

1. **Never commit `.env` files**
   - Already in `.gitignore`
   - Contains real credentials

2. **Don't hardcode credentials in code**
```python
# BAD
config = ConnectionConfig(api_key="actual-key-in-code")

# GOOD
config = ConnectionConfig.from_env()
```

3. **Don't share `.env` files**
   - Each developer should have their own
   - Use a secrets manager for teams

---

## Troubleshooting

### Error: "organization_id must be provided"

Make sure your `.env` file has:
```bash
DEEPLYNX_ORG_ID=123
```

### Error: "Must provide either jwt_token or both api_key and api_secret"

Add authentication credentials to `.env`:
```bash
DEEPLYNX_KEY=your-key
DEEPLYNX_SECRET=your-secret
```

### .env File Not Loading

1. Check file location: `ls -la .env`
2. Check file contents: `cat .env`
3. Try explicit path:
```python
config = ConnectionConfig.from_env(env_file=Path(".env"))
```

### Environment Variables Not Found

Check if they're set:
```bash
printenv | grep DEEPLYNX
printenv | grep AGENT
```

---

## Docker Integration

### Dockerfile
```dockerfile
FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Don't copy .env - use environment variables
CMD ["python", "agent.py"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  agent:
    build: .
    environment:
      # Agent
      - AGENT_PORT=8000
      - AGENT_SECRET=${AGENT_SECRET}
      # StorageClient
      - DEEPLYNX_KEY=${DEEPLYNX_KEY}
      - DEEPLYNX_SECRET=${DEEPLYNX_SECRET}
      - DEEPLYNX_ORG_ID=123
      - DEEPLYNX_PROJECT_ID=456
    env_file:
      - .env  # Can also load from file
```

### Run with environment variables
```bash
docker run \
  -e AGENT_SECRET=your-secret \
  -e DEEPLYNX_KEY=your-key \
  -e DEEPLYNX_SECRET=your-secret \
  -e DEEPLYNX_ORG_ID=123 \
  -e DEEPLYNX_PROJECT_ID=456 \
  your-image
```

---

## CI/CD Integration

### GitHub Actions
```yaml
name: Tests

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        env:
          DEEPLYNX_KEY: ${{ secrets.DEEPLYNX_KEY }}
          DEEPLYNX_SECRET: ${{ secrets.DEEPLYNX_SECRET }}
          DEEPLYNX_ORG_ID: 123
          DEEPLYNX_PROJECT_ID: 456
          AGENT_SECRET: ${{ secrets.AGENT_SECRET }}
        run: pytest
```

---

## Summary

| Component | Prefix | Key Variables |
|-----------|--------|---------------|
| PrometheusAgent | `AGENT_` | `AGENT_PORT`, `AGENT_HOST`, `AGENT_SECRET` |
| StorageClient | `DEEPLYNX_` | `DEEPLYNX_KEY`, `DEEPLYNX_SECRET`, `DEEPLYNX_ORG_ID` |

Quick start:
```bash
cp .env.example .env  # Copy template
vim .env              # Add credentials
python your_script.py # Use it!
```
