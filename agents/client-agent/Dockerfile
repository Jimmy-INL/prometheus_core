FROM python:3.11-slim

# Accept proxy as build args
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Set proxy environment variables for pip
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

# Set up CA certificate bundle: start with system certs, append custom if provided
COPY --from=certs . /tmp/certs/
RUN cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem 2>/dev/null || true && \
    if ls /tmp/certs/*.pem 1> /dev/null 2>&1; then \
        cat /tmp/certs/*.pem >> /etc/ssl/certs/ca-bundle.pem; \
    fi && rm -rf /tmp/certs

# Set SSL cert environment variables for pip and runtime
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem

WORKDIR /app

# Copy prometheus_api from local submodule
COPY --from=prometheus_api . /tmp/prometheus_api

# Install dependencies
COPY pyproject.toml /app/
RUN pip install --no-cache-dir --default-timeout=100 \
    "/tmp/prometheus_api[agent]" .

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
