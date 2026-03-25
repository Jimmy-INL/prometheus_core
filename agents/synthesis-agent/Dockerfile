FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api:latest

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

# Set SSL cert environment variables for dependency installation and runtime
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem
ENV UV_NATIVE_TLS=true
ENV UV_CERT_FILE=/etc/ssl/certs/ca-bundle.pem

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT="/usr/local"

# Install dependencies
COPY pyproject.toml /app/
RUN uv sync --no-dev --no-install-project --inexact

COPY agent.py /app/agent.py
COPY agent_card.json /app/agent_card.json

EXPOSE 8000

CMD ["python", "agent.py"]
