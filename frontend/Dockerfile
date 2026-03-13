FROM python:3.13-slim

# Accept proxy as build args
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

WORKDIR /app

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

# Install CA certs if provided — rename .pem → .crt so update-ca-certificates picks them up
COPY --from=certs . /tmp/certs/
RUN if ls /tmp/certs/*.pem 1>/dev/null 2>&1; then \
        for f in /tmp/certs/*.pem; do \
            cp "$f" "/usr/local/share/ca-certificates/$(basename "${f%.pem}").crt"; \
        done && \
        update-ca-certificates; \
    fi && rm -rf /tmp/certs

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Point uv at the system cert bundle (includes any custom CAs added above)
ENV UV_NATIVE_TLS=true
ENV UV_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Copy project files
COPY frontend/pyproject.toml frontend/uv.lock ./
RUN uv sync --no-dev --frozen

# Copy application code
COPY frontend/ .

EXPOSE 8500

# Use the venv directly to avoid uv downloading a Python interpreter at runtime
CMD ["/app/.venv/bin/chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8500"]
