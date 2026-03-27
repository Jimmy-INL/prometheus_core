FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api:latest

# Accept proxy as build args
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# Set proxy environment variables for pip
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

# Install system dependencies (libX11 etc. required by VTK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

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
COPY frontend/pyproject.toml frontend/uv.lock /app/
RUN uv sync --no-dev --frozen --no-install-project --inexact

# .dockerignore prevents additional files from being copied.
COPY frontend/. /app/.

EXPOSE 8500

CMD ["chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8500"]
