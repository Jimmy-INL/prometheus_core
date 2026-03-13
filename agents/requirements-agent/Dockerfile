FROM python:3.11-slim

# Accept proxy settings as build arguments
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Set proxy environment variables if provided
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
COPY pyproject.toml .
COPY nucsys_agent/ ./nucsys_agent/
RUN pip install --no-cache-dir --default-timeout=100 \
    "/tmp/prometheus_api[agent]" .

# Copy agent entrypoint and card
COPY agent.py .
COPY agent_card.json .

# Note: Port is configured via AGENT_PORT environment variable (default: 8000)
# For multi-agent deployments, use unique ports per agent (8000, 8001, 8002, etc.)
# with matching internal/external Docker port mappings (-p 8001:8001)
EXPOSE 8000

# Run the agent
CMD ["python", "agent.py"]
