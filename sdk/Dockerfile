FROM python:3.12-slim

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /tmp

# Set up CA certificate bundle: start with system certs, append custom if provided
COPY certs /tmp/certs/
RUN cp /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.pem 2>/dev/null || true && \
    if ls /tmp/certs/*.pem 1> /dev/null 2>&1; then \
        cat /tmp/certs/*.pem >> /etc/ssl/certs/ca-bundle.pem; \
    fi && rm -rf /tmp/certs


RUN python -m pip install --upgrade pip uv

COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
    /src[agent,tracing]

RUN rm -rf /src/.git
CMD ["python"]
