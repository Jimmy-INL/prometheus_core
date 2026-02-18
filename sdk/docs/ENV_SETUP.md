# Environment Variable Setup Guide

## Quick Setup

1. **Copy the template:**
```bash
cp .env.example .env
```

2. **Edit `.env` with your credentials:**
```bash
# Open in your editor
vim .env
# or
nano .env
```

3. **Fill in your actual values:**

Add your credentials to the `.env` file:
- `DEEPLYNX_KEY` - Your API key
- `DEEPLYNX_SECRET` - Your API secret
- `DEEPLYNX_ORG_ID` - Your organization ID
- `DEEPLYNX_PROJECT_ID` - Your project ID

4. **Use in your code:**
```python
from prometheus_api.storage_client import ConnectionConfig, StorageClient

# Automatically loads from .env
config = ConnectionConfig.from_env()

with StorageClient(config) as client:
    items = client.items.list()
```

## Environment Variables Reference

### Required Variables

#### Authentication (choose one method)

**Option 1: API Key/Secret (Recommended)**
```bash
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret
```

**Option 2: JWT Token**
```bash
DEEPLYNX_JWT_TOKEN=your-jwt-token
```

#### Organization & Project
```bash
DEEPLYNX_ORG_ID=123          # Your organization ID (integer)
DEEPLYNX_PROJECT_ID=456      # Your project ID (integer)
```

### Optional Variables

```bash
# Custom API endpoint (defaults to INL DeepLynx)
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1

# Connection settings
DEEPLYNX_TIMEOUT=30.0        # Request timeout in seconds
DEEPLYNX_MAX_RETRIES=3       # Number of retry attempts
DEEPLYNX_VERIFY_SSL=true     # SSL certificate verification
```

## Usage Patterns

### 1. Load from Default .env File

```python
from prometheus_api.storage_client import ConnectionConfig

# Loads from .env in current directory
config = ConnectionConfig.from_env()
```

### 2. Load from Specific File

```python
from pathlib import Path

# Load from a specific location
config = ConnectionConfig.from_env(
    env_file=Path("/path/to/production.env")
)
```

### 3. Override Specific Values

```python
# Load from .env but override org/project
config = ConnectionConfig.from_env(
    organization_id=999,  # Override env var
    project_id=888,       # Override env var
    timeout=60.0          # Custom timeout
)
```

### 4. Multiple Environments

**Development (.env.dev):**
```bash
DEEPLYNX_KEY=dev-key
DEEPLYNX_SECRET=dev-secret
DEEPLYNX_ORG_ID=100
DEEPLYNX_PROJECT_ID=200
DEEPLYNX_BASE_URL=https://dev.deeplynx.com/api/v1
```

**Production (.env.prod):**
```bash
DEEPLYNX_KEY=prod-key
DEEPLYNX_SECRET=prod-secret
DEEPLYNX_ORG_ID=500
DEEPLYNX_PROJECT_ID=600
DEEPLYNX_BASE_URL=https://deeplynx.inl.gov/api/v1
```

**Load based on environment:**
```python
import os
from pathlib import Path

env = os.getenv("APP_ENV", "dev")
env_file = Path(f".env.{env}")

config = ConnectionConfig.from_env(env_file=env_file)
```

## Security Best Practices

### ✅ DO

1. **Use `.env` files for local development**
```bash
# .env is gitignored by default
cp .env.example .env
# Edit with your credentials
```

2. **Use environment variables in production**
```bash
# Set in your deployment system
export DEEPLYNX_KEY=prod-key
export DEEPLYNX_SECRET=prod-secret
```

3. **Keep `.env.example` updated**
```bash
# Template without actual credentials
DEEPLYNX_KEY=your-api-key-here
DEEPLYNX_SECRET=your-api-secret-here
```

4. **Use different credentials per environment**
```bash
# Development
.env.dev

# Staging
.env.staging

# Production
.env.prod
```

### ❌ DON'T

1. **Never commit `.env` files**
   - Already in `.gitignore`
   - Contains real credentials

2. **Don't hardcode credentials in code**
```python
# ❌ BAD
config = ConnectionConfig(
    api_key="actual-key-in-code",  # Don't do this!
    ...
)

# ✅ GOOD
config = ConnectionConfig.from_env()
```

3. **Don't share `.env` files**
   - Each developer should have their own
   - Use a secrets manager for teams

## Troubleshooting

### Error: "organization_id must be provided"

Make sure your `.env` file has:
```bash
DEEPLYNX_ORG_ID=123
```

Or provide it manually:
```python
config = ConnectionConfig.from_env(organization_id=123)
```

### Error: "Must provide either jwt_token or both api_key and api_secret"

You need authentication credentials. Add to `.env`:
```bash
DEEPLYNX_KEY=your-key
DEEPLYNX_SECRET=your-secret
```

### .env File Not Loading

1. Check file location:
```bash
ls -la .env
```

2. Check file contents:
```bash
cat .env
```

3. Try explicit path:
```python
from pathlib import Path
config = ConnectionConfig.from_env(env_file=Path(".env"))
```

### Environment Variables Not Found

Check if they're set:
```bash
printenv | grep DEEPLYNX
```

Or in Python:
```python
import os
print(os.getenv("DEEPLYNX_KEY"))
```

## Docker Integration

### Dockerfile
```dockerfile
FROM python:3.11

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . .

# Don't copy .env - use environment variables
CMD ["python", "your_script.py"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  app:
    build: .
    environment:
      - DEEPLYNX_KEY=${DEEPLYNX_KEY}
      - DEEPLYNX_SECRET=${DEEPLYNX_SECRET}
      - DEEPLYNX_ORG_ID=123
      - DEEPLYNX_PROJECT_ID=456
    env_file:
      - .env  # Can also load from file
```

### Run with environment variables
```bash
docker run \
  -e DEEPLYNX_KEY=your-key \
  -e DEEPLYNX_SECRET=your-secret \
  -e DEEPLYNX_ORG_ID=123 \
  -e DEEPLYNX_PROJECT_ID=456 \
  your-image
```

## CI/CD Integration

### GitHub Actions
```yaml
name: Tests

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        env:
          DEEPLYNX_KEY: ${{ secrets.DEEPLYNX_KEY }}
          DEEPLYNX_SECRET: ${{ secrets.DEEPLYNX_SECRET }}
          DEEPLYNX_ORG_ID: 123
          DEEPLYNX_PROJECT_ID: 456
        run: pytest
```

### GitLab CI
```yaml
test:
  script:
    - pip install -r requirements.txt
    - pytest
  variables:
    DEEPLYNX_KEY: $DEEPLYNX_KEY
    DEEPLYNX_SECRET: $DEEPLYNX_SECRET
    DEEPLYNX_ORG_ID: "123"
    DEEPLYNX_PROJECT_ID: "456"
```

## Example Scripts

See `examples/env_config_usage.py` for complete working examples including:
- Loading from default .env
- Loading from specific files
- Overriding parameters
- Multiple environments
- Error handling

Run it:
```bash
python examples/env_config_usage.py
```

## Summary

Environment variables provide:
- ✅ Security (credentials not in code)
- ✅ Flexibility (easy to change environments)
- ✅ Best practices (industry standard)
- ✅ CI/CD friendly (works with all platforms)

Start using them:
```bash
cp .env.example .env  # Copy template
vim .env              # Add credentials
python your_script.py # Use it!
```
