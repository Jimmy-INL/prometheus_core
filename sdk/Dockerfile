################################################################################
## install target: Installed prometheus_api (default target)

################################################################################
FROM docker.io/python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9 AS install

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem \
    UV_SYSTEM_PYTHON=1

# Set up CA certificate bundle: start with system certs, append custom if provided
RUN --mount=type=bind,source=certs,target=/tmp/certs \
    cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem 2>/dev/null || true; \
    if ls /tmp/certs/*.pem 1>/dev/null 2>&1; then \
        cat /tmp/certs/*.pem >> /etc/ssl/certs/ca-bundle.pem; \
    fi

# Install uv for python management
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install uv

# Install only dependencies (not including dev dependencies)
# This is kept separately because it will change less often than
# the next run command (when the source actually cnanges)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=/src/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/src/uv.lock \
    cd /src && \
    uv export --frozen --no-dev --no-emit-project > requirements.txt && \
    uv pip install -r requirements.txt

# Install prometheus_api into python site-packages
RUN --mount=type=bind,source=pyproject.toml,target=/src/pyproject.toml \
    --mount=type=bind,source=prometheus_api,target=/src/prometheus_api/ \
    cd /src && \
    uv pip install --no-deps /src

# Default entrypoint is python
CMD ["python"]

################################################################################
## install-dev target: Installed prometheus_api + development dependencies
################################################################################

FROM install AS install-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=/src/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/src/uv.lock \
    cd /src && \
    uv export --frozen --only-dev > requirements.txt && \
    uv pip install -r requirements.txt

################################################################################
## default target: Put this last so that "install" becomes the default
################################################################################
FROM install AS default
