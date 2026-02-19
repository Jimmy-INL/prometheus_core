# TEMPLATE_NAME Agent

A2A-enabled agent template for building specialized agents.

## Overview

This agent implements the Agent-to-Agent (A2A) protocol, allowing it to communicate with other agents in a multi-agent system. It includes INL's storage client and agent utilities, and can be easily customized for your specific use case.

## Features

- **A2A Protocol**: Full implementation of Agent-to-Agent communication standard
- **Storage Client & Agent Utils**: Pre-integrated with INL's storage_client and agent packages
- **Progress Updates**: Built-in support for long-running tasks with incremental progress reporting
- **Registry Integration**: Automatic registration with agent registry for discovery
- **Docker Support**: Complete containerization with health checks
- **Proxy & SSL Support**: Enterprise-ready with proxy and custom CA certificate support
- **Customizable**: Easy-to-modify template for your specific domain

## Architecture

```
┌─────────────────┐
│  Agent Client   │
└────────┬────────┘
         │ A2A Protocol (JSON-RPC 2.0)
         ▼
┌─────────────────┐      ┌──────────────┐
│  TEMPLATE_NAME  │◄────►│   Registry   │
│     Agent       │      │   Service    │
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│ Prometheus API  │
│ (Your Logic)    │
└─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Anthropic API key

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

   Generate a new secret
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Update `AGENT_SECRET` in .env with this new secret

3. **Run the agent:**
   ```bash
   python agent.py
   ```

The agent will start on `http://localhost:8000` by default.

### Docker Deployment

1. **Build the image:**
   ```bash
   docker build -t TEMPLATE_SLUG-agent .
   ```

2. **Run the container:**

   **Option A: Use .env file**
   ```bash
   docker run -p 8000:8000 --env-file .env TEMPLATE_SLUG-agent
   ```

   **Option B: Pass environment variables explicitly**
   ```bash
   docker run -p 8000:8000 \
     -e AGENT_PORT=8000 \
     -e REGISTRY_URL=http://registry:8000 \
     TEMPLATE_SLUG-agent
   ```

   Note: The `.env` file is NOT copied into the Docker image. You must either use `--env-file` to load it at runtime or pass variables with `-e` flags.

**Docker Port Mapping - Important Design Decision:**

There are two approaches to port configuration:

**Approach A: Matching Internal/External Ports (Recommended)**
Each agent uses a unique port that's the same inside and outside the container:
```bash
# Each agent listens on its own port (internal = external)
docker run -p 8000:8000 -e AGENT_PORT=8000 client-agent
docker run -p 8001:8001 -e AGENT_PORT=8001 plant-agent
docker run -p 8002:8002 -e AGENT_PORT=8002 data-agent
```

**Benefits:**
- Consistent port numbers across containerized and non-containerized deployments
- `AGENT_PORT` means the same thing everywhere
- Agent card URL accurately reflects how to reach the agent
- Simpler mental model

**Approach B: Fixed Internal Port with Docker Mapping**
All agents listen on 8000 internally, Docker maps to different external ports:
```bash
# All agents listen internally on 8000
docker run -p 8000:8000 -e AGENT_PORT=8000 client-agent
docker run -p 8001:8000 -e AGENT_PORT=8000 plant-agent  # ⚠️ Agent card shows :8000
docker run -p 8002:8000 -e AGENT_PORT=8000 data-agent   # ⚠️ Agent card shows :8000
```

**Trade-off:** Agent card advertises `:8000` but external clients use `:8001`, `:8002`, etc.

**Recommendation:** Use Approach A for consistency across deployment modes.

### Docker Compose Integration

Add this service to your `docker-compose.yml`:

**Recommended: Matching Internal/External Ports**
```yaml
services:
  TEMPLATE_SLUG-agent:
    build:
      context: ./TEMPLATE_SLUG-agent
      additional_contexts:
        certs: ${CA_CERT_DIR:-./certs}
      args:
        - HTTP_PROXY=${HTTP_PROXY}
        - HTTPS_PROXY=${HTTPS_PROXY}
        - NO_PROXY=${NO_PROXY}
    environment:
      - AGENT_PORT=8002  # Port the agent listens on (internal = external)
      - AGENT_HOST=TEMPLATE_SLUG-agent  # Service name for inter-agent communication
      - REGISTRY_URL=http://registry:8000
      - SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
      - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
    ports:
      - "8002:8002"  # Same port internally and externally
    depends_on:
      registry:
        condition: service_healthy
    networks:
      - agent-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:${AGENT_PORT:-8002}/health', timeout=5.0)"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  agent-network:
    driver: bridge
```

**Why Matching Ports?**
- Consistent across containerized and non-containerized deployments
- Agent card advertises `http://TEMPLATE_SLUG-agent:8002`, which accurately reflects how to reach it
- Simpler configuration - `AGENT_PORT` means the same thing everywhere

**Multi-Agent Example:**
```yaml
services:
  client-agent:
    environment:
      - AGENT_PORT=8000
      - AGENT_HOST=client-agent
    ports:
      - "8000:8000"

  plant-agent:
    environment:
      - AGENT_PORT=8001
      - AGENT_HOST=plant-agent
    ports:
      - "8001:8001"

  data-agent:
    environment:
      - AGENT_PORT=8002
      - AGENT_HOST=data-agent
    ports:
      - "8002:8002"
```

Each agent's card advertises the correct port, and inter-agent communication works seamlessly.

## Containerized vs Non-Containerized Deployment

**The Conundrum:**

This template supports both containerized (Docker) and non-containerized (local) deployments, which creates a configuration challenge around port management.

### Non-Containerized (Local Development)

Running directly with Python:
```bash
AGENT_PORT=8000 python agent.py
```

- Agent listens on: `localhost:8000`
- Agent card advertises: `http://localhost:8000`
- Other agents connect to: `http://localhost:8000`

**Simple and straightforward** - the port you set is the port used everywhere.

### Containerized (Docker)

Running in a container introduces Docker's port mapping:
```bash
docker run -p <external>:<internal> agent
```

This creates two port numbers:
- **Internal port**: What the agent process listens on inside the container
- **External port**: What's exposed on the host machine

### The Design Decision

**Option 1: Matching Ports (Recommended)**
```yaml
ports: "8002:8002"
environment:
  - AGENT_PORT=8002
```
- Agent listens internally on 8002
- Exposed externally on 8002
- Agent card advertises: `http://service-name:8002`
- ✅ Consistent across deployment modes
- ✅ Agent card URL is accurate
- ⚠️ Each agent needs a unique port

**Option 2: Fixed Internal Port**
```yaml
ports: "8002:8000"
environment:
  - AGENT_PORT=8000
```
- Agent listens internally on 8000 (all agents the same)
- Exposed externally on 8002 (different per agent)
- Agent card advertises: `http://service-name:8000`
- ✅ Dockerfile can hardcode port 8000
- ⚠️ External clients use 8002, but agent card says 8000
- ⚠️ Inconsistent with non-containerized mode

### Why We Recommend Option 1

**Consistency** is more valuable than having a standard internal port. The agent card URL should accurately reflect how to reach the agent, and `AGENT_PORT` should mean the same thing whether running locally or in Docker.

**Implementation:**
- Set `AGENT_PORT` to a unique value for each agent (8000, 8001, 8002, etc.)
- Use matching Docker port mapping: `-p 8001:8001`
- The agent will listen on and advertise the same port
- Works identically in local and Docker deployments

## Customization Guide

### 1. Update Agent Metadata

The agent card is loaded from `agent_card.json` (single source of truth). Edit this file to customize:

- **name**: Your agent's display name
- **description**: Brief description of what your agent does
- **version**: Agent version number
- **skills**: List of capabilities your agent provides

Example `agent_card.json`:
```json
{
  "name": "My Custom Agent",
  "description": "Performs custom analysis tasks",
  "url": "http://localhost:8000",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [...]
}
```

Note: The `url` field is automatically overridden at runtime based on `AGENT_PORT` and `AGENT_HOST` environment variables.

### 2. Define Input Schema

In `process_analysis()` method, customize the parameters your agent expects:

```python
def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
    # Extract your custom parameters
    my_param = params.get("my_param")
    another_param = params.get("another_param")

    # Your logic here
    ...
```

Update the `inputSchema` in `agent_card.json` to match:

```python
"inputSchema": {
    "type": "object",
    "properties": {
        "my_param": {
            "type": "string",
            "description": "Description of my_param"
        },
        "another_param": {
            "type": "number",
            "description": "Description of another_param"
        }
    },
    "required": ["my_param"]
}
```

### 3. Customize the Analysis Logic

The `process_analysis()` method contains your agent's core logic:

```python
def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
    # Extract your parameters
    input_data = params.get("input_data")

    # Use storage_client or your custom logic
    result = StorageClient().items.get(input_data)

    # Add metadata
    result.update({
        "agent": "TEMPLATE_NAME",
        "timestamp": datetime.utcnow().isoformat()
    })

    return result
```

### 4. Long-Running Tasks with Progress Updates

For long-running tasks, use the `event_queue` to send progress updates:

```python
def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
    steps = ["Loading data", "Processing", "Finalizing"]

    for i, step in enumerate(steps):
        # Send progress update
        progress = (i + 1) / len(steps) * 100
        event_queue.put({
            "type": "status",
            "status": "working",
            "message": f"{step}... ({progress:.0f}% complete)"
        })

        # Do the work
        perform_step(step)

        # Optional: Send intermediate results
        event_queue.put({
            "type": "artifact",
            "data": json.dumps({"step": step, "result": "..."})
        })

    return final_result
```

The template includes a commented example in `agent.py` that you can uncomment and modify.

### 6. Define Skills

Skills represent the capabilities your agent exposes. Edit the `skills` array in `agent_card.json`:

```json
{
  "skills": [
    {
      "id": "my_analysis_skill",
      "name": "My Analysis Skill",
      "description": "Performs analysis of X using Y methodology",
      "inputSchema": {
        "type": "object",
        "properties": {
          "param1": {
            "type": "string",
            "description": "Description of param1"
          }
        },
        "required": ["param1"]
      }
    },
    {
      "id": "another_skill",
      "name": "Another Skill",
      "description": "Does something else",
      "inputSchema": { }
    }
  ]
}
```

The agent loads this configuration at startup and advertises these skills to the registry.

### 7. Add Custom Dependencies

The template includes `prometheus_api` with storage client and agent utilities pre-installed:

```python
# Already available in the template
from prometheus_api.storage_client import StorageClient
from prometheus_api.agent.middleware import BearerTokenMiddleware
```

If your agent needs additional Python packages, add them to `requirements.txt`:

```
# Your custom dependencies
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
```

## API Endpoints

### Health Check
```
GET /health
```
Returns agent health status.

### Agent Card
```
GET /.well-known/agent.json
```
Returns the agent card describing capabilities.

### Message (A2A Protocol)
```
POST /message
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "request-uuid",
  "params": {
    "message": {
      "messageId": "msg-uuid",
      "role": "user",
      "parts": [
        {
          "text": "{\"input_data\": \"your data here\"}"
        }
      ]
    }
  }
}
```

## Testing

### Testing Locally

```bash
# Start the agent
python agent.py

# In another terminal, test with curl
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "test-1",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "user",
        "parts": [
          {
            "text": "{\"input_data\": \"test data\"}"
          }
        ]
      }
    }
  }'
```

### Testing with Docker

```bash
# Build and run
docker build -t TEMPLATE_SLUG-agent .
docker run -p 8000:8000 TEMPLATE_SLUG-agent

# Test
curl http://localhost:8000/health
```

## Security: Shared Secret Authentication

### Overview

All agents in a deployment share a secret token to prevent unauthorized access. This ensures users cannot access agents belonging to other users in multi-tenant environments.

### Configuration

1. **Generate a strong secret:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set AGENT_SECRET for all agents:**
   ```bash
   # In .env file or environment
   AGENT_SECRET=xK8mP2vR9jQ4nL7wT5bN3hD6fS1gA0cY8zE
   ```

3. **Use the same secret across all agents in your deployment**

### How It Works

- All incoming HTTP requests must include: `Authorization: Bearer <secret>`
- Requests without valid Bearer token receive `401 Unauthorized`
- Agents automatically add the Bearer token to outgoing requests (e.g., registry registration)
- Health check endpoint (`/health`) and agent card (`/.well-known/agent.json`) are exempt from authentication

### Docker Compose Example

```yaml
services:
  client-agent:
    environment:
      - AGENT_SECRET=${AGENT_SECRET}  # Shared across all agents
      - AGENT_PORT=8000

  plant-agent:
    environment:
      - AGENT_SECRET=${AGENT_SECRET}  # Same secret
      - AGENT_PORT=8001
```

### Best Practices

- **Use a unique secret per deployment** - don't share secrets across user environments
- **Keep secrets in environment variables** - never commit to version control
- **Rotate secrets periodically** - update all agents simultaneously
- **Use strong secrets** - minimum 32 characters, cryptographically random
- **Disable authentication only for local development** - set `AGENT_SECRET_REQUIRED=false`

### Security Notes

- Bearer tokens are sent in HTTP headers (not encrypted by default)
- Consider using HTTPS/TLS in production (or nginx proxy with TLS)
- This prevents cross-user access but not man-in-the-middle attacks without TLS
- For stronger security, deploy agents on isolated networks or use TLS

### Development Mode (No Authentication)

For local development, you can disable authentication:

```bash
# In .env file
AGENT_SECRET_REQUIRED=false
```

This allows requests without Bearer tokens. **Never use this in production.**

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port the agent listens on (use unique values per agent: 8000, 8001, etc.) | `8000` | Yes |
| `AGENT_HOST` | Hostname for agent card URL (use Docker service name for containerized deployments) | `localhost` | Yes |
| `AGENT_SECRET` | Shared secret for Bearer token authentication (generate with secrets.token_urlsafe(32)) | - | Yes (production) |
| `AGENT_SECRET_REQUIRED` | Whether to enforce authentication (set to 'false' only for local dev) | `true` | No |
| `REGISTRY_URL` | URL of the agent registry | `http://registry:8000` | No |
| `HTTP_PROXY` | HTTP proxy URL | - | No |
| `HTTPS_PROXY` | HTTPS proxy URL | - | No |
| `NO_PROXY` | Comma-separated list of hosts to bypass proxy | - | No |
| `SSL_CERT_FILE` | Path to SSL certificate bundle | `/etc/ssl/certs/ca-bundle.pem` | No |

**Port Configuration:**
- **Local deployment**: `AGENT_PORT=8000`, agent listens on `localhost:8000`
- **Docker deployment**: `AGENT_PORT=8001` with `-p 8001:8001` (matching ports recommended)
- **Multi-agent systems**: Use unique ports per agent (8000, 8001, 8002, etc.)

**Hostname Configuration:**
- **Local deployment**: `AGENT_HOST=localhost`
- **Docker deployment**: `AGENT_HOST=service-name` (e.g., `plant-agent`)

The agent card advertises `http://{AGENT_HOST}:{AGENT_PORT}`, which other agents use for communication.

## Troubleshooting

### Registry registration fails

**Issue**: `Failed to register with registry`

**Solution**:
- Ensure the registry service is running
- Check the `REGISTRY_URL` environment variable
- The agent will continue to run even if registration fails

### SSL certificate errors in corporate environments

**Issue**: `SSLError` or certificate validation failures

**Solution**:
1. Export your corporate CA certificate
2. Place it in a `certs` directory
3. Build with: `docker build --build-context certs=./certs -t TEMPLATE_SLUG-agent .`

### Proxy configuration

**Issue**: Can't connect to external services through corporate proxy

**Solution**: Set proxy environment variables:
```bash
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1,registry
```

## Project Structure

```
TEMPLATE_SLUG-agent/
├── agent.py              # Main agent implementation
├── Dockerfile            # Docker container configuration
├── requirements.txt      # Python dependencies
├── agent_card.json       # Agent metadata and capabilities (loaded at runtime)
├── .env.example          # Example environment configuration
└── README.md            # This file
```

**Agent Card Loading:** The agent loads `agent_card.json` at startup via `create_agent_card()` in `agent.py`. The URL field is automatically updated based on `AGENT_PORT` and `AGENT_HOST` environment variables to reflect the actual runtime configuration. This makes `agent_card.json` the single source of truth for agent metadata, capabilities, and skills.

## A2A Protocol Reference

This agent implements the A2A (Agent-to-Agent) protocol, which uses JSON-RPC 2.0 over HTTP for communication.

### Message Format

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "<request-id>",
  "params": {
    "message": {
      "messageId": "<message-id>",
      "role": "user",
      "parts": [
        {"text": "<json-encoded-parameters>"}
      ]
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": "<request-id>",
  "result": {
    "artifacts": [
      {
        "parts": [
          {"text": "<json-encoded-result>"}
        ]
      }
    ]
  }
}
```

### Status Updates

The agent sends status updates through the event queue:
- `working`: Agent is processing the request
- `completed`: Agent has finished successfully
- `failed`: Agent encountered an error

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## Support

[Add support information here]
