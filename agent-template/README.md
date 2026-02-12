# Prometheus Agent Template

A comprehensive template for creating A2A (Agent-to-Agent) enabled AI agents using Claude and the A2A SDK.

## Overview

This repository provides a production-ready template for building specialized AI agents that can communicate with each other using the Agent-to-Agent (A2A) protocol. The template is based on the architecture used in the `nuclear-a2a-demo` project and includes everything you need to get started.

## Features

- **A2A Protocol Support**: Full implementation of the Agent-to-Agent communication standard
- **Claude Integration**: Uses Anthropic's Claude for intelligent processing
- **Registry Integration**: Automatic registration with agent registry for service discovery
- **Docker Ready**: Complete containerization with health checks and enterprise features
- **Enterprise Support**: Proxy and custom CA certificate support for corporate environments
- **Easy Customization**: Simple setup script to create new agents without manual find/replace

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Anthropic API key

### Creating a New Agent

Use the interactive setup script to create a new agent:

```bash
python setup_agent.py
```

The script will guide you through the process:
1. Agent name (e.g., "Weather Analysis")
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

Agent name (e.g., 'Weather Analysis', 'Data Validator'): Weather Analysis

Agent description (brief summary of what it does) [A specialized agent for weather analysis]: Analyzes weather patterns and provides forecasts

Agent slug (used for directories and Docker) [weather-analysis]:

Agent class name (PascalCase) [WeatherAnalysis]:

----------------------------------------------------------------------
  Primary Skill Configuration
----------------------------------------------------------------------

Primary skill ID (snake_case) [weather_analysis_analysis]: analyze_weather

Primary skill name [Weather Analysis Analysis]: Analyze Weather Pattern

Primary skill description [Performs analysis using weather analysis]: Analyzes weather data and generates forecasts

Output directory [./weather-analysis]:

======================================================================
  Configuration Summary
======================================================================

Agent Name:        Weather Analysis
Description:       Analyzes weather patterns and provides forecasts
Slug:              weather-analysis
Class Name:        WeatherAnalysis
Primary Skill ID:  analyze_weather
Primary Skill:     Analyze Weather Pattern
Output Directory:  ./weather-analysis

Proceed with these settings? (yes/no) [yes]: yes

Creating agent in './weather-analysis'...

  ✓ agent.py
  ✓ Dockerfile
  ✓ requirements.txt
  ✓ .env.example
  ✓ agent_card.json
  ✓ README.md

======================================================================
  Agent Created Successfully!
======================================================================

Your new agent has been created in: ./weather-analysis

Next steps:
  1. cd ./weather-analysis
  2. cp .env.example .env
  3. Edit .env and add your ANTHROPIC_API_KEY
  4. Install dependencies: pip install -r requirements.txt
  5. Run the agent: python agent.py

Or use Docker:
  1. docker build -t weather-analysis ./weather-analysis
  2. docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key weather-analysis

For more information, see the README.md in your agent directory.
```

### Running Your Agent

#### Local Development

```bash
cd ./your-agent-name
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
pip install -r requirements.txt
python agent.py
```

#### Docker

```bash
docker build -t your-agent-slug ./your-agent-name
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key your-agent-slug
```

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

### 1. Customize the Analysis Logic

Edit the `process_analysis()` method in `agent.py`:

```python
def process_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
    # Extract your custom parameters
    my_param = params.get("my_param")

    # Your custom logic here
    result = self._do_something_with(my_param)

    return result
```

### 2. Update the Prompt

Modify the `_build_prompt()` method to create domain-specific prompts for Claude:

```python
def _build_prompt(self, input_data: str, params: Dict[str, Any]) -> str:
    prompt = f"""You are an expert in [YOUR DOMAIN].

Analyze the following data:
{input_data}

Provide your analysis in JSON format:
{{
    "field1": "value1",
    "field2": ["item1", "item2"]
}}
"""
    return prompt
```

### 3. Define Additional Skills

Update the `create_agent_card()` method to define multiple skills:

```python
"skills": [
    {
        "id": "skill_1",
        "name": "First Skill",
        "description": "Does X",
        "inputSchema": { ... }
    },
    {
        "id": "skill_2",
        "name": "Second Skill",
        "description": "Does Y",
        "inputSchema": { ... }
    }
]
```

### 4. Add Custom Dependencies

The template includes `prometheus_api` pre-installed from INL's GitHub Enterprise:

```python
# Already available in the template
import prometheus_api
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
│  Claude API     │
│  (Anthropic)    │
└─────────────────┘
```

### Key Components

1. **AgentExecutor**: Handles A2A protocol communication and message routing
2. **Agent Card**: Describes the agent's capabilities and skills
3. **Registry Integration**: Automatic registration for service discovery
4. **Claude Integration**: Intelligent processing using Claude API

## A2A Protocol

The template implements the full A2A protocol specification:

### Message Format

**Request:**
```json
{
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
}
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
      - AGENT_PORT=8000
      - REGISTRY_URL=http://registry:8000
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MODEL_NAME=${MODEL_NAME:-claude-sonnet-4-20250514}
      - SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
      - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
    ports:
      - "8002:8000"
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

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key | - | Yes |
| `MODEL_NAME` | Claude model | `claude-sonnet-4-20250514` | No |
| `AGENT_PORT` | Port to run on | `8000` | No |
| `REGISTRY_URL` | Registry service URL | `http://registry:8000` | No |
| `HTTP_PROXY` | HTTP proxy | - | No |
| `HTTPS_PROXY` | HTTPS proxy | - | No |
| `NO_PROXY` | Proxy bypass list | - | No |

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
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your_key test-agent
curl http://localhost:8000/health
```

## Example Agents

The `nuclear-a2a-demo` directory contains example agents:
- **data-agent**: Material property data retrieval
- **corrosion-agent**: Corrosion analysis
- **radiation-agent**: Radiation damage assessment
- **thermal-agent**: Thermal analysis
- **client-agent**: LangGraph orchestrator

Study these for real-world implementation patterns.

## Troubleshooting

### Common Issues

**ANTHROPIC_API_KEY not set**
```
ValueError: ANTHROPIC_API_KEY environment variable is required
```
Solution: Set the environment variable or add it to `.env`

**Registry connection fails**
```
Failed to register with registry
```
Solution: Ensure the registry service is running. The agent will continue without registration.

**SSL/TLS errors**
```
SSLError: certificate verify failed
```
Solution: Add your corporate CA certificate to the `certs` directory and rebuild.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

[Add your license here]

## References

- [A2A SDK Documentation](https://github.com/anthropics/anthropic-sdk-python)
- [Claude API Documentation](https://docs.anthropic.com/)
- [Docker Documentation](https://docs.docker.com/)

## Support

For issues or questions:
1. Check the agent-specific README in your created agent directory
2. Review the nuclear-a2a-demo example agents
3. Open an issue in this repository
