FROM python:3.12-slim

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1


# Set up CA certificate bundle: start with system certs, append custom if provided
RUN --mount=type=bind,source=certs,target=/tmp/certs \
    cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem 2>/dev/null || true && \
    if ls /tmp/certs/*.pem 1> /dev/null 2>&1; then \
        cat /tmp/certs/*.pem >> /etc/ssl/certs/ca-bundle.pem; \
    fi

RUN python -m pip install --upgrade pip uv

# Step 1: install only third-party dependencies (cache-stable)
COPY pyproject.toml uv.lock /src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project -o /src/requirements.txt --project /src && \
    uv pip install --system -r /src/requirements.txt

# Step 2: install the local package (invalidates when source changes)
COPY prometheus_api/ /src/prometheus_api/
COPY README.md /src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-deps /src

COPY tests /src/tests

CMD ["python"]
