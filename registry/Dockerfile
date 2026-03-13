FROM python:3.11-slim

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

# Set SSL cert environment variables for pip and runtime
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem

WORKDIR /app

# Install dependencies with increased timeout
RUN pip install --no-cache-dir \
    --default-timeout=100 \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    pydantic>=2.5.3 \
    httpx>=0.26.0

COPY app.py /app/app.py

EXPOSE 8000

CMD ["python", "app.py"]
