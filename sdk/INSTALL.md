# Installation Guide

## Install from Git Repository

### Basic Installation

```bash
pip install git+https://github.inl.gov/genesis/prometheus_api.git
```

### Install with Development Dependencies

```bash
pip install "git+https://github.inl.gov/genesis/prometheus_api.git#egg=storage-client[dev]"
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
git+https://github.inl.gov/genesis/prometheus_api.git#egg=storage-client[dev]
```

## Using in pyproject.toml

For projects using `pyproject.toml`:

```toml
[project]
dependencies = [
    "storage-client @ git+https://github.inl.gov/genesis/prometheus_api.git",
]
```

## Using with Poetry

```bash
poetry add git+https://github.inl.gov/genesis/prometheus_api.git
```

Or in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
storage-client = {git = "https://github.inl.gov/genesis/prometheus_api.git"}
```

## Using with pip-tools

In `requirements.in`:

```
storage-client @ git+https://github.inl.gov/genesis/prometheus_api.git
```

Then:

```bash
pip-compile requirements.in
pip-sync requirements.txt
```

## Verify Installation

After installation, verify it works:

```python
python -c "import storage_client; print(f'Version: {storage_client.__version__}')"
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
pip uninstall storage-client
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
FROM python:3.11

WORKDIR /app

# Install storage-client from git
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
cp .env.example .env  # If you have the example file
vim .env  # Add your DeepLynx credentials
```

Or create `.env` manually:
```bash
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret
DEEPLYNX_ORG_ID=1
DEEPLYNX_PROJECT_ID=32
```

2. **Use the library:**
```python
from storage_client import ConnectionConfig, StorageClient, ItemCreate

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

# Set up pre-commit hooks (optional)
pip install pre-commit
pre-commit install

# Run tests
pytest tests/ -v
```

## Questions?

See:
- README.md - User guide
- QUICK_START.md - Quick reference
- TESTING.md - Testing guide
