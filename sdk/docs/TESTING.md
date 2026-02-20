# Testing Guide

## Quick Start

```bash
# Install dependencies (includes test dependencies)
pip install -e ".[dev,agent]"

# Run all unit tests (no external dependencies required)
pytest

# Run only integration tests (requires .env with credentials)
pytest -m integration

# Run tests excluding integration tests
pytest -m "not integration"
```

## Test Organization

Tests are organized by component:

| File | Description | Marker |
|------|-------------|--------|
| `test_agent.py` | A2A agent executor and event handling | unit |
| `test_connection.py` | Connection configuration | unit |
| `test_models.py` | Data models (Item, Relationship, etc.) | unit |
| `test_exceptions.py` | Custom exceptions | unit |
| `test_env_config.py` | Environment variable loading | unit |
| `test_integration.py` | Full API integration tests | integration |

## Running Tests

### All Tests
```bash
pytest
```

### By Marker
```bash
# Unit tests only (fast, no external dependencies)
pytest -m "not integration"

# Integration tests only (requires .env)
pytest -m integration

# Slow tests excluded
pytest -m "not slow"
```

### Specific Test File
```bash
pytest tests/test_agent.py
pytest tests/test_models.py
```

### Specific Test Class or Function
```bash
pytest tests/test_agent.py::TestPrometheusAgentExecutor
pytest tests/test_agent.py::TestPrometheusAgentExecutor::test_execute_calls_enqueue_event
```

### With Coverage
```bash
pytest --cov=prometheus_api --cov-report=html
open htmlcov/index.html
```

## Integration Tests Setup

Integration tests require a connection to a DeepLynx database.

### 1. Create .env file
```bash
cp .env.example .env
```

### 2. Configure credentials
```bash
# Required
DEEPLYNX_KEY=your-api-key
DEEPLYNX_SECRET=your-api-secret
DEEPLYNX_ORG_ID=1
DEEPLYNX_PROJECT_ID=32

# Optional (auto-fetched if not specified)
DEEPLYNX_DATA_SOURCE_ID=32
```

### 3. Run integration tests
```bash
pytest -m integration
```

## Test Markers

Markers are defined in `pyproject.toml`:

- `unit` - Unit tests with no external dependencies
- `integration` - Tests requiring database connection
- `slow` - Long-running tests

Tests in `test_integration.py` are automatically marked with `integration`.

## Writing Tests

### Unit Test Example
```python
def test_item_create():
    """Test creating ItemCreate model."""
    item = ItemCreate(
        name="Test Item",
        properties={"key": "value"}
    )
    assert item.name == "Test Item"
```

### Async Test Example
```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test async functionality."""
    result = await some_async_function()
    assert result is not None
```

### Integration Test Example
```python
@pytest.mark.integration
def test_api_connection(client):
    """Test API connectivity."""
    items = client.items.list()
    assert items is not None
```

## Troubleshooting

### "No module named 'a2a'" or "'starlette'"
Install agent dependencies:
```bash
pip install -e ".[agent]"
```

### Integration tests skip
Create a `.env` file with valid credentials.

### "DataSource with id 0 not found"
Add `DEEPLYNX_DATA_SOURCE_ID` to your `.env` file.

### Async test warnings
Async tests use `asyncio_mode = "auto"` in `pyproject.toml`. No need for explicit `@pytest.mark.asyncio` decorators.

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -e ".[dev,agent]"

      - name: Run unit tests
        run: pytest -m "not integration"

      - name: Run integration tests
        if: github.event_name == 'push'
        env:
          DEEPLYNX_KEY: ${{ secrets.DEEPLYNX_KEY }}
          DEEPLYNX_SECRET: ${{ secrets.DEEPLYNX_SECRET }}
          DEEPLYNX_ORG_ID: ${{ secrets.DEEPLYNX_ORG_ID }}
          DEEPLYNX_PROJECT_ID: ${{ secrets.DEEPLYNX_PROJECT_ID }}
        run: pytest -m integration
```
