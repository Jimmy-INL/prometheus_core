# syntax=docker/dockerfile:1
ARG PROMETHEUS_API_BASE_IMAGE_HASH=latest
FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:${PROMETHEUS_API_BASE_IMAGE_HASH}

RUN --mount=type=cache,id=prometheus-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=prometheus-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libglib2.0-0 \
    libgomp1

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT="/usr/local" \
    UV_LINK_MODE=copy

COPY frontend/pyproject.toml frontend/uv.lock /app/
RUN --mount=type=cache,id=prometheus-uv-cache,target=/root/.cache/uv,sharing=locked \
    uv sync --no-dev --frozen --no-install-project --inexact

RUN python -c "import a2a.server.routes, prometheus_api.agent"

COPY frontend/. /app/.

EXPOSE 8500

CMD ["chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8500"]
