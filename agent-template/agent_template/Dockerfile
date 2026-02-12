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

# Expose port (default: 8000)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5.0)" || exit 1

# Run the agent
CMD ["python", "agent.py"]
