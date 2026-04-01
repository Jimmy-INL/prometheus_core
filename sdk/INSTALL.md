# Installation Guide

## Install from Git Repository

### Basic Installation

```bash
pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

### Install with Agent Support

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]"
```

### Install Specific Version/Branch

```bash
# Install from a specific branch
pip install git+https://github.inl.gov/genesis/prometheus_api.git@main

# Install from a specific commit
pip install git+https://github.inl.gov/genesis/prometheus_api.git@475268d

# Install from a specific tag (when available)
pip install git+https://github.inl.gov/genesis/prometheus_api.git@v0.1.0
```

### Install in Editable Mode (for Development)

```bash
# Clone the repository first
git clone https://github.inl.gov/genesis/prometheus_api.git
cd prometheus_api

# Install in editable mode
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

## Using in requirements.txt

Add to your project's `requirements.txt`:

```
# Direct installation
git+https://github.inl.gov/genesis/prometheus_api.git

# Or with version/branch
git+https://github.inl.gov/genesis/prometheus_api.git@main

# Or with extras
git+https://github.inl.gov/genesis/prometheus_api.git#egg=prometheus-api[agent]
```

## Using in pyproject.toml

For projects using `pyproject.toml`:

```toml
[project]
dependencies = [
    "prometheus-api @ git+https://github.inl.gov/genesis/prometheus_api.git",
]
```

## Using with Poetry

```bash
poetry add git+https://github.inl.gov/genesis/prometheus_api.git
```

Or in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
prometheus-api = {git = "https://github.inl.gov/genesis/prometheus_api.git"}
```

## Using with pip-tools

In `requirements.in`:

```
prometheus-api @ git+https://github.inl.gov/genesis/prometheus_api.git
```

Then:

```bash
pip-compile requirements.in
pip-sync requirements.txt
```

## Verify Installation

After installation, verify it works:

```python
python -c "from prometheus_api.storage_client import StorageClient; print('OK')"
```

Or run the verification script (if cloned):

```bash
python verify_installation.py
```

## Authentication for Private Repository

If the repository is private, you may need to authenticate:

### Using SSH

```bash
pip install git+ssh://git@github.inl.gov/genesis/prometheus_api.git
```

### Using Personal Access Token

```bash
pip install git+https://<token>@github.inl.gov/genesis/prometheus_api.git
```

### Using Git Credential Manager

Configure git credentials, then:

```bash
pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

## Uninstall

```bash
pip uninstall prometheus-api
```

## Upgrade

```bash
# Upgrade to latest
pip install --upgrade git+https://github.inl.gov/genesis/prometheus_api.git

# Force reinstall
pip install --force-reinstall git+https://github.inl.gov/genesis/prometheus_api.git
```

## Docker Installation

In your `Dockerfile`:

```dockerfile
FROM python:3.12

WORKDIR /app

# Install prometheus-api from git
RUN pip install git+https://github.inl.gov/genesis/prometheus_api.git

# Copy your application
COPY . .

CMD ["python", "your_app.py"]
```

## Common Issues

### SSL Certificate Errors

```bash
pip install --trusted-host github.inl.gov git+https://github.inl.gov/genesis/prometheus_api.git
```

### Authentication Required

If you get authentication errors:
1. Set up git credentials
2. Use SSH instead of HTTPS
3. Use a personal access token in the URL

### Package Not Found

Make sure:
1. The repository URL is correct
2. You have access to the repository
3. The repository is pushed to the remote

## After Installation

1. **Set up credentials:**
```bash
cp .env.example .env
vim .env  # Add your DeepLynx credentials
```

2. **Use the library:**
```python
from prometheus_api.storage_client import ConnectionConfig, StorageClient, ItemCreate

config = ConnectionConfig.from_env()

with StorageClient(config) as client:
    item = client.items.create(ItemCreate(
        name="My Item",
        description="Description",
        properties={"key": "value"}
    ))
    print(f"Created: {item.id}")
```

## Development Installation

For contributors:

```bash
# Clone
git clone https://github.inl.gov/genesis/prometheus_api.git
cd prometheus_api

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Further Reading

- [README.md](README.md) - Overview and quick start
- [StorageClient Guide](docs/storage-client/GUIDE.md) - Full StorageClient documentation
- [PrometheusAgent Guide](docs/agent/GUIDE.md) - Full agent documentation
- [Testing Guide](docs/TESTING.md) - Running and writing tests
