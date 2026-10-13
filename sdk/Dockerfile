FROM ghcr.io/astral-sh/uv:0.11.25-python3.12-trixie-slim@sha256:1b9ee30381d729b07044688631ba4473c72db5c048a5f2a504c40186e65efb86

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem \
    UV_SYSTEM_PYTHON=1

# Set up CA certificate bundle: start with system certs, append custom if provided
RUN --mount=type=bind,source=certs,target=/tmp/certs \
    mkdir -p /usr/local/share/ca-certificates; \
    find /tmp/certs -maxdepth 1 -type f \( -name '*.pem' -o -name '*.crt' \) -exec sh -c '\
        for cert do \
            name="$(basename "$cert")"; \
            case "$name" in \
                *.pem) name="${name%.pem}.crt" ;; \
            esac; \
            cp "$cert" "/usr/local/share/ca-certificates/$name"; \
        done \
    ' sh {} +; \
    update-ca-certificates; \
    cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem

# Install git
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install only dependencies (not including dev dependencies)
# This is kept separately because it will change less often than
# the next run command (when the source actually cnanges)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=/src/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/src/uv.lock \
    cd /src && \
    uv export --frozen --no-dev --no-emit-project > requirements.txt && \
    uv pip install -r requirements.txt && \
    rm requirements.txt

# Install prometheus_api into python site-packages
RUN --mount=type=bind,source=pyproject.toml,target=/src/pyproject.toml \
    --mount=type=bind,source=prometheus_api,target=/src/prometheus_api/ \
    cd /src && \
    uv pip install --no-deps /src && \
    rm -rf /src/build *.egg-info

# Default entrypoint is python
CMD ["python"]
