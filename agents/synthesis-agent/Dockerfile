FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT="/usr/local"

# Install dependencies
COPY pyproject.toml /app/
RUN uv sync --no-dev --no-install-project --inexact

COPY agent.py /app/agent.py
COPY agent_card.json /app/agent_card.json

EXPOSE 8000

CMD ["python", "agent.py"]
