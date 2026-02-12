# TEMPLATE_NAME Agent

A2A-enabled agent template for building specialized AI agents.

## Overview

This agent implements the Agent-to-Agent (A2A) protocol, allowing it to communicate with other agents in a multi-agent system. It uses Claude (Anthropic's AI) for intelligent processing and can be easily customized for your specific use case.

## Features

- **A2A Protocol**: Full implementation of Agent-to-Agent communication standard
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
│  Claude API     │
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
   # Edit .env and add your ANTHROPIC_API_KEY
   ```

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
   ```bash
   docker run -p 8000:8000 \
     -e ANTHROPIC_API_KEY=your_api_key \
     -e REGISTRY_URL=http://registry:8000 \
     TEMPLATE_SLUG-agent
   ```

### Docker Compose Integration

Add this service to your `docker-compose.yml`:

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
      - AGENT_PORT=8000
      - REGISTRY_URL=http://registry:8000
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MODEL_NAME=${MODEL_NAME:-claude-sonnet-4-20250514}
      - SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
      - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
    ports:
      - "8000:8000"
    depends_on:
      registry:
        condition: service_healthy
    networks:
      - agent-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health', timeout=5.0)"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  agent-network:
    driver: bridge
```

## Customization Guide

### 1. Update Agent Metadata

Edit the following in `agent.py`:

- **TEMPLATE_NAME**: Your agent's display name
- **TEMPLATE_CLASS**: Your agent's class name (PascalCase)
- **TEMPLATE_DESCRIPTION**: Brief description of what your agent does

### 2. Define Input Schema

In `process_analysis()` method, customize the parameters your agent expects:

```python
def process_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
    # Extract your custom parameters
    my_param = params.get("my_param")
    another_param = params.get("another_param")

    # Your logic here
    ...
```

Update the `inputSchema` in `create_agent_card()` to match:

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

The `_build_prompt()` method constructs the prompt sent to Claude. Customize it for your domain:

```python
def _build_prompt(self, input_data: str, params: Dict[str, Any]) -> str:
    prompt = f"""You are an expert in [YOUR DOMAIN].

Analyze the following [YOUR DATA TYPE]:
{input_data}

Context:
{json.dumps(params, indent=2)}

Provide your analysis in JSON format with the following structure:
{{
    "field1": "value1",
    "field2": ["item1", "item2"],
    ...
}}
"""
    return prompt
```

### 4. Define Skills

Skills represent the capabilities your agent exposes. Edit `create_agent_card()`:

```python
"skills": [
    {
        "id": "my_analysis_skill",
        "name": "My Analysis Skill",
        "description": "Performs analysis of X using Y methodology",
        "inputSchema": { ... }
    },
    {
        "id": "another_skill",
        "name": "Another Skill",
        "description": "Does something else",
        "inputSchema": { ... }
    }
]
```

### 5. Add Custom Dependencies

The template includes `prometheus_api` pre-installed:

```python
# Already available in the template
import prometheus_api
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
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key TEMPLATE_SLUG-agent

# Test
curl http://localhost:8000/health
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | - | Yes |
| `MODEL_NAME` | Claude model to use | `claude-sonnet-4-20250514` | No |
| `AGENT_PORT` | Port to run the agent on | `8000` | No |
| `REGISTRY_URL` | URL of the agent registry | `http://registry:8000` | No |
| `HTTP_PROXY` | HTTP proxy URL | - | No |
| `HTTPS_PROXY` | HTTPS proxy URL | - | No |
| `NO_PROXY` | Comma-separated list of hosts to bypass proxy | - | No |
| `SSL_CERT_FILE` | Path to SSL certificate bundle | `/etc/ssl/certs/ca-bundle.pem` | No |

## Troubleshooting

### Agent won't start

**Issue**: `ValueError: ANTHROPIC_API_KEY environment variable is required`

**Solution**: Ensure you've set the `ANTHROPIC_API_KEY` environment variable or added it to your `.env` file.

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
├── agent_card.json       # Agent metadata and capabilities
├── .env.example          # Example environment configuration
└── README.md            # This file
```

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
