# syntax=docker/dockerfile:1
# Standalone FastAPI chat backend. Built FROM the prometheus_api base image (same
# as the agents) because the app imports prometheus_api.{a2a_stream,contract,
# storage_client} at runtime, and that package is preinstalled in the base image.
#
# `prometheus-api` is a dev-only dependency in pyproject.toml, pinned to a private
# git branch via [tool.uv.sources] for local tests. At image build time we must NOT
# fetch that private repo, so:
#   --no-dev       exclude the dev group (we don't reinstall prometheus-api)
#   --no-sources   ignore [tool.uv.sources] entirely, so uv never clones the git
#                  repo while resolving the lock (the deciding flag — --no-dev alone
#                  still resolves the source)
#   --inexact      keep the prometheus-api + deps already preinstalled in the image
#   --no-install-project  don't install chat-backend itself; the code is COPYed below
ARG PROMETHEUS_API_BASE_IMAGE_HASH
FROM containers.github.inl.gov/genesis/prometheus_api:${PROMETHEUS_API_BASE_IMAGE_HASH}

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT="/usr/local" \
    UV_LINK_MODE=copy

COPY pyproject.toml /app/
RUN --mount=type=cache,id=prometheus-uv-cache,target=/root/.cache/uv,sharing=locked \
    uv sync --no-dev --no-install-project --inexact --no-sources

# Brings app/config.yml along with the package sources.
COPY app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
