FROM python:3.11-slim

# Accept proxy settings as build arguments
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Set proxy environment variables if provided
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install CA certificates if provided
# This allows for custom SSL certificates in corporate environments
COPY --from=certs . /tmp/certs/ || true
RUN if [ -d /tmp/certs ]; then \
        cat /etc/ssl/certs/ca-certificates.crt /tmp/certs/*.pem > /etc/ssl/certs/ca-bundle.pem 2>/dev/null || \
        cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem; \
    else \
        cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem; \
    fi

# Set SSL certificate environment variables
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY agent.py .

# Note: Port is configured via AGENT_PORT environment variable (default: 8000)
# For multi-agent deployments, use unique ports per agent (8000, 8001, 8002, etc.)
# with matching internal/external Docker port mappings (-p 8001:8001)
EXPOSE 8000

# Health check - uses AGENT_PORT if set, otherwise defaults to 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, httpx; port = os.getenv('AGENT_PORT', '8000'); httpx.get(f'http://localhost:{port}/health', timeout=5.0)" || exit 1

# Run the agent
CMD ["python", "agent.py"]
