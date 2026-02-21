# Prometheus Agent Template

This repository provides a production-ready template for building specialized AI agents that can communicate with each other using the Agent-to-Agent (A2A) protocol using the A2A SDK with INL's storage client and agent utilities. 

## Features

- **A2A Protocol Support**: Full implementation of the Agent-to-Agent communication standard
- **Shared Secret Authentication**: Built-in Bearer token authentication for multi-tenant security
- **Storage Client & Agent Utils**: Pre-integrated with INL's storage_client and agent packages
- **Progress Updates**: Built-in support for long-running tasks with incremental progress reporting
- **Registry Integration**: Automatic registration with agent registry for service discovery
- **Docker Ready**: Complete containerization with health checks and enterprise features
- **Enterprise Support**: Proxy and custom CA certificate support for corporate environments
- **Easy Customization**: Simple setup script to create new agents without manual find/replace

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (optional, for containerized deployment)

### Creating a New Agent

Clone this repository
```bash
git clone git@github.inl.gov:genesis/prometheus_agent_template.git
```

Use the interactive setup script to create a new agent:

```bash
python setup_agent.py
```

The script will guide you through the process:
1. Agent name (e.g., "Plant Analysis")
2. Description
3. Slug (for directories/Docker)
4. Class name
5. Primary skill configuration
6. Output directory

Example:
```bash
$ python setup_agent.py

======================================================================
  Agent Template Setup
======================================================================

This script will help you create a new agent from the template.
Please provide the following information:

Agent name (e.g., 'Plant Analysis', 'Data Validator'): Plant Analysis

Agent description (brief summary of what it does) [A specialized agent for balance of plant analysis]: Analyzes balance of plant systems for nuclear facilities

Agent slug (used for directories and Docker) [plant-analysis]:

Agent class name (PascalCase) [PlantAnalysis]:

----------------------------------------------------------------------
  Primary Skill Configuration
----------------------------------------------------------------------

Primary skill ID (snake_case) [plant_analysis_analysis]: analyze_plant

Primary skill name [Plant Analysis Analysis]: Analyze Balance of Plant

Primary skill description [Performs balance of plant system analysis]: Analyzes balance of plant systems including turbines, condensers, and cooling systems

Output directory [./plant-analysis]:

======================================================================
  Configuration Summary
======================================================================

Agent Name:        Plant Analysis
Description:       Analyzes balance of plant systems for nuclear facilities
Slug:              plant-analysis
Class Name:        PlantAnalysis
Primary Skill ID:  analyze_plant
Primary Skill:     Analyze Balance of Plant
Output Directory:  ./plant-analysis

Proceed with these settings? (yes/no) [yes]: yes

Creating agent in './plant-analysis'...

  ✓ agent.py
  ✓ Dockerfile
  ✓ requirements.txt
  ✓ .env.example
  ✓ agent_card.json
  ✓ README.md

======================================================================
  Agent Created Successfully!
======================================================================

Your new agent has been created in: ./plant-analysis

Next steps:
  1. cd ./plant-analysis
  2. cp .env.example .env
  3. Generate an AGENT_SECRET
    ```bash
    python -c "import secrets; print(secrets.token_urlsafe(32))"
    ```
  4. Update AGENT_SECRET in .env
  5. Install dependencies: pip install -r requirements.txt
  6. Run the agent: python agent.py

Or use Docker:
  1. docker build -t plant-analysis ./plant-analysis
  2. docker run -p 8000:8000 --env-file ./plant-analysis/.env plant-analysis
     (or pass env vars: docker run -p 8000:8000 -e AGENT_PORT=8000 plant-analysis)

For more information, see the README.md in your agent directory.
```

### Running Your Agent

#### Local Development

```bash
cd ./your-agent-name
cp .env.example .env
# Edit .env if needed
pip install -r requirements.txt
python agent.py
```

#### Docker

```bash
docker build -t your-agent-slug ./your-agent-name

# Option A: Use .env file
docker run -p 8000:8000 --env-file ./your-agent-name/.env your-agent-slug

# Option B: Pass environment variables explicitly
docker run -p 8000:8000 \
  -e AGENT_PORT=8000 \
  -e REGISTRY_URL=http://registry:8000 \
  your-agent-slug
```

Note: The `.env` file is NOT copied into Docker images. Use `--env-file` or `-e` flags to pass configuration.

## Template Structure

```
agent_template/
├── agent.py              # Main agent implementation
├── Dockerfile            # Docker container configuration
├── requirements.txt      # Python dependencies
├── agent_card.json       # Agent metadata and capabilities
├── .env.example          # Example environment configuration
└── README.md            # Agent-specific documentation
```

## Customization Guide

After creating your agent, you'll want to customize it for your specific use case:

### 1. Update Agent Metadata (agent_card.json)

The agent card is loaded from `agent_card.json` at runtime. This file serves as the single source of truth for:
- Agent name and description
- Version number
- Capabilities (streaming, push notifications)
- Skills (available operations with input/output schemas)

Edit `agent_card.json`:
```json
{
  "name": "My Custom Agent",
  "description": "Performs custom analysis",
  "version": "1.0.0",
  "skills": [
    {
      "id": "my_skill",
      "name": "My Skill",
      "description": "Does something useful",
      "inputSchema": {
        "type": "object",
        "properties": {
          "my_param": {"type": "string"}
        }
      }
    }
  ]
}
```

**Note:** The `url` field is automatically updated at runtime based on `AGENT_PORT` and `AGENT_HOST` environment variables.

### 2. Customize the Analysis Logic

Edit the `process_analysis()` method in `agent.py`:

```python
async def process_analysis(
    self,
    params: Dict[str, Any],
    context: RequestContext,
    event_queue: EventQueue,
) -> Dict[str, Any]:
    # Extract your custom parameters
    my_param = params.get("my_param")

    # Use storage_client or your custom logic
    result = StorageClient().items.get(my_param)

    return result
```

### 3. Long-Running Tasks with Progress Updates

For long-running tasks, use the `event_queue` to send progress updates:

```python
async def process_analysis(
    self,
    params: Dict[str, Any],
    context: RequestContext,
    event_queue: EventQueue,
) -> Dict[str, Any]:
    steps = ["Step 1", "Step 2", "Step 3"]

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

        # Do the work
        await perform_step(step)

    return final_result
```

### 4. Define Additional Skills

Add multiple skills to the `skills` array in `agent_card.json`:

```json
{
  "skills": [
    {
      "id": "skill_1",
      "name": "First Skill",
      "description": "Does X",
      "inputSchema": {
        "type": "object",
        "properties": {
          "input": {"type": "string"}
        }
      }
    },
    {
      "id": "skill_2",
      "name": "Second Skill",
      "description": "Does Y",
      "inputSchema": {
        "type": "object",
        "properties": {
          "data": {"type": "number"}
        }
      }
    }
  ]
}
```

### 5. Add Custom Dependencies

The template includes `prometheus_api` with storage client and agent utilities pre-installed from INL's GitHub Enterprise:

```python
# Already available in the template
from prometheus_api.storage_client import StorageClient
from prometheus_api.agent.middleware import BearerTokenMiddleware
```

Add any additional Python packages to `requirements.txt`:

```
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
```

## Architecture

The template implements a standard A2A agent architecture:

```
┌─────────────────┐
│  Agent Client   │
│  (Orchestrator) │
└────────┬────────┘
         │ A2A Protocol
         │ (JSON-RPC 2.0)
         ▼
┌─────────────────┐      ┌──────────────┐
│  Your Agent     │◄────►│   Registry   │
│                 │      │   Service    │
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│ Storage Client  │
│ (Your Logic)    │
└─────────────────┘
```

### Key Components

1. **AgentExecutor**: Handles A2A protocol communication and message routing
2. **Agent Card**: Describes the agent's capabilities and skills
3. **Registry Integration**: Automatic registration for service discovery
4. **Storage Client & Agent Utils**: Pre-integrated for data processing and agent utilities
5. **Progress Updates**: Event queue for real-time status and progress reporting

## A2A Protocol

The template implements the full A2A protocol specification:

### Message Format

**Request:**
```bash
curl -X POST http://0.0.0.0:8000 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "request-123",
    "params": {
      "message": {
        "messageId": "msg-456",
        "role": "user",
        "parts": [
          {"text": "{\"input_data\": \"your data\"}"}
        ]
      }
    }
  }'
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "result": {
    "artifacts": [
      {
        "parts": [
          {"text": "{\"result\": \"analysis output\"}"}
        ]
      }
    ]
  }
}
```

## Docker Compose Integration

To integrate your agent into a multi-agent system, add it to `docker-compose.yml`:

```yaml
services:
  your-agent:
    build:
      context: ./your-agent-name
      additional_contexts:
        certs: ${CA_CERT_DIR:-./certs}
      args:
        - HTTP_PROXY=${HTTP_PROXY}
        - HTTPS_PROXY=${HTTPS_PROXY}
        - NO_PROXY=${NO_PROXY}
    environment:
      - AGENT_PORT=8001  # Port the agent listens on (internal = external)
      - AGENT_HOST=your-agent  # Service name for inter-agent communication
      - REGISTRY_URL=http://registry:8000
      - SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
      - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
    ports:
      - "8001:8001"  # Same port internally and externally (recommended)
    depends_on:
      registry:
        condition: service_healthy
    networks:
      - agent-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:${AGENT_PORT:-8001}/health', timeout=5.0)"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  agent-network:
    driver: bridge
```

### Port Configuration: Containerized vs Non-Containerized

**The Conundrum:**

This template supports both containerized (Docker) and non-containerized (local) deployments. The key decision is whether to use matching or different internal/external ports.

**Recommended Approach: Matching Ports**

Use the same port number inside and outside the container:
```yaml
environment:
  - AGENT_PORT=8001
ports:
  - "8001:8001"  # Same port internally and externally
```

**Benefits:**
- ✅ Consistent across containerized and non-containerized deployments
- ✅ Agent card URL accurately reflects how to reach the agent
- ✅ `AGENT_PORT` means the same thing everywhere
- ✅ Simpler mental model

**Alternative Approach: Fixed Internal Port**

All agents use port 8000 internally, Docker maps to different external ports:
```yaml
environment:
  - AGENT_PORT=8000
ports:
  - "8001:8000"  # Different external (8001) and internal (8000)
```

**Trade-offs:**
- ⚠️ Agent card advertises `:8000` but external access uses `:8001`
- ⚠️ Inconsistent with non-containerized mode
- ✅ All containers use same internal port

**Multi-Agent Example (Matching Ports):**
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

Each agent advertises its actual reachable URL through its agent card.

## Security: Shared Secret Authentication

The template includes built-in support for shared secret authentication using Bearer tokens. All agents in a deployment share the same secret, preventing unauthorized cross-user access in multi-tenant environments.

### Quick Setup

1. **Generate a strong secret:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set the same secret for all agents:**
   ```bash
   # In your .env file or docker-compose.yml
   AGENT_SECRET=your-generated-secret-here
   ```

3. **All agents will automatically:**
   - Verify Bearer tokens on incoming requests
   - Include Bearer tokens in outgoing requests (registry registration, inter-agent calls)
   - Reject unauthorized requests with 401 Unauthorized

### How It Works

- **Incoming requests** must include: `Authorization: Bearer <your_token>`
- **Outgoing requests** automatically include the Bearer token header
- **Health checks** (`/health`) and **agent cards** (`/.well-known/agent.json`) are exempt
- **Development mode**: Set `AGENT_SECRET_REQUIRED=false` to disable authentication locally

### Docker Compose Example

```yaml
services:
  client-agent:
    environment:
      - AGENT_SECRET=${AGENT_SECRET}  # Shared across all agents
      - AGENT_PORT=8000
    ports:
      - "8000:8000"

  plant-agent:
    environment:
      - AGENT_SECRET=${AGENT_SECRET}  # Same secret
      - AGENT_PORT=8001
    ports:
      - "8001:8001"
```

### Security Best Practices

- Use unique secrets per deployment (per user/environment)
- Never commit secrets to version control
- Use strong, cryptographically random secrets (32+ characters)
- Rotate secrets periodically
- Consider TLS/HTTPS in production for encryption in transit
- Only disable authentication for local development

For complete documentation, see the Security section in your agent's README after creation.

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_PORT` | Port the agent listens on (use unique values per agent: 8000, 8001, etc.) | `8000` | Yes |
| `AGENT_HOST` | Hostname for agent card URL (use Docker service name for containerized) | `localhost` | Yes |
| `AGENT_SECRET` | Shared secret for Bearer token authentication (generate with secrets.token_urlsafe(32)) | - | Yes (production) |
| `AGENT_SECRET_REQUIRED` | Whether to enforce authentication (set to 'false' only for local dev) | `true` | No |
| `REGISTRY_URL` | Registry service URL | `http://registry:8000` | No |
| `HTTP_PROXY` | HTTP proxy | - | No |
| `HTTPS_PROXY` | HTTPS proxy | - | No |
| `NO_PROXY` | Proxy bypass list | - | No |

**Configuration Guidelines:**
- **Local deployment**: `AGENT_PORT=8000`, `AGENT_HOST=localhost`
- **Docker deployment**: `AGENT_PORT=8001`, `AGENT_HOST=your-agent` with `-p 8001:8001`
- **Multi-agent**: Assign unique ports (8000, 8001, 8002, etc.) with matching Docker mappings

The agent card advertises `http://{AGENT_HOST}:{AGENT_PORT}` for inter-agent communication.

## Enterprise Features

### Proxy Support

The template supports HTTP/HTTPS proxies for corporate environments:

```bash
docker build \
  --build-arg HTTP_PROXY=http://proxy.company.com:8080 \
  --build-arg HTTPS_PROXY=http://proxy.company.com:8080 \
  -t your-agent .
```

### Custom CA Certificates

For corporate SSL inspection:

1. Place your CA certificate in a `certs` directory
2. Build with: `docker build --build-context certs=./certs -t your-agent .`

The Dockerfile will automatically bundle it with system certificates.

## Testing

### Local Testing

```bash
# Start the agent
python agent.py

# Test with curl
curl -X POST http://localhost:8000/message \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your_token>" \
    -d '{
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "test-1",
        "params": {
        "message": {
            "messageId": "msg-1",
            "role": "user",
            "parts": [{"text": "{\"input_data\": \"test\"}"}]
        }
        }
    }'
```

### Docker Testing

```bash
docker build -t test-agent .
docker run -p 8000:8000 test-agent
curl -H "Authorization: Bearer <your_token>" http://localhost:8000/health
```

### Testing with Prometheus a2a-tester

1. Install a2a-tester
    ```bash
    git clone https://github.inl.gov/genesis/a2a-tester
    cd a2a-tester
    uv sync
    uv run python app.py
    ```

2. Open your web browser to (http://127.0.0.1:8501).
3. In the URL box, enter the URL of your A2A agent. By default it is: (http://0.0.0.0:8000/).
4. Enter your authorization token. This is what was set when you started your agent.
5. Click "Fetch Agent Card".

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## References

- [A2A SDK Documentation](https://github.com/anthropics/anthropic-sdk-python)
- [Claude API Documentation](https://docs.anthropic.com/)
- [Docker Documentation](https://docs.docker.com/)

## Support

For issues or questions:
1. Reach out on Teams
