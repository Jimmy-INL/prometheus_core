FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT="/usr/local"

# Install dependencies
COPY pyproject.toml /app/
RUN uv sync --no-dev --no-install-project --inexact

COPY agent.py /app/agent.py
COPY agent_card.json /app/agent_card.json
COPY artifact_handling.py /app/artifact_handling.py
COPY conversation_store.py /app/conversation_store.py
COPY tool_discovery.py /app/tool_discovery.py
COPY capability_cache.py /app/capability_cache.py
COPY param_schema.py /app/param_schema.py
COPY planner.py /app/planner.py
COPY workflow_library /app/workflow_library
COPY workflows /app/workflows

EXPOSE 8000

CMD ["python", "agent.py"]
