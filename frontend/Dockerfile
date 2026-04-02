FROM mooseharbor.hpc.inl.gov/prometheus_api/prometheus_api-py312:latest

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

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT="/usr/local"

# Install dependencies
COPY frontend/pyproject.toml frontend/uv.lock /app/
RUN uv sync --no-dev --frozen --no-install-project --inexact

# .dockerignore prevents additional files from being copied.
COPY frontend/. /app/.

EXPOSE 8500

CMD ["chainlit", "run", "main.py", "--host", "0.0.0.0", "--port", "8500"]
