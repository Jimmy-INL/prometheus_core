# Storage Client Testing Guide

## Test Suite Overview

The storage client has both unit tests and integration tests:

- **Unit Tests**: Test individual components without external dependencies
- **Integration Tests**: Test against a real DeepLynx database using .env credentials

## Integration Test Suite

### Setup

1. **Create .env file with credentials:**
```bash
cp .env.example .env
vim .env
```

Required variables:
- `DEEPLYNX_KEY`
- `DEEPLYNX_SECRET`
- `DEEPLYNX_ORG_ID`
- `DEEPLYNX_PROJECT_ID`
- `DEEPLYNX_DATA_SOURCE_ID` (optional - will auto-fetch default)

2. **Install test dependencies:**
```bash
pip install pytest pytest-asyncio
```

### Running Tests

**Run all integration tests:**
```bash
python -m pytest tests/test_integration.py -v
```

**Run using the helper script:**
```bash
./run_integration_tests.sh
```

**Run specific test classes:**
```bash
# Authentication tests only
pytest tests/test_integration.py::TestAuthentication -v

# Item creation tests
pytest tests/test_integration.py::TestItemCreation -v

# Pagination tests
pytest tests/test_integration.py::TestPagination -v
```

**Run quick verification:**
```bash
python test_connection.py
```

### Test Coverage

The integration test suite covers:

#### ✅ Authentication (3 tests)
- Configuration loading from .env
- Client connection
- Data source auto-fetching

#### ✅ Item Creation (3 tests)
- Single item creation
- Item creation with all fields
- Bulk item creation

#### ✅ Item Retrieval (2 tests)
- Get item by ID
- List items with pagination

#### ✅ Pagination (3 tests)
- Page info correctness
- Multiple page retrieval
- Automatic iteration with iter_all()

#### ✅ Item Updates (2 tests)
- Update item name
- Update item properties

#### ✅ Cleanup (2 tests)
- Delete items
- Clean up orphaned test items

#### ⏭️ Search (2 tests - skipped if not configured)
- Search query
- Recent items search

#### ⏭️ Relationships (2 tests - skipped if not configured)
- Create relationships
- Get item relationships

**Total: 19 tests (15 passed, 4 skipped)**

### Test Item Marking

All test items are marked with special properties for safe cleanup:
- `_test_suite_marker`: "storage-client-test-suite"
- `_test_run_id`: Unique timestamp for each test run

This ensures:
- Test items can be identified and cleaned up
- No accidental deletion of real data
- Orphaned items from failed runs can be found

### Cleanup Behavior

**Automatic cleanup:**
- Test items are deleted after each test module completes
- Uses pytest fixtures for setup/teardown

**Manual cleanup:**
The `test_cleanup_orphaned_items` test finds and deletes test items from previous failed runs.

**Verify cleanup:**
```bash
# Check for remaining test items
python << 'EOF'
from storage_client import ConnectionConfig, StorageClient
config = ConnectionConfig.from_env()
with StorageClient(config) as client:
    recent = client.search.recent(limit=50)
    test_items = [i for i in recent if i.properties.get("_test_suite_marker")]
    print(f"Test items remaining: {len(test_items)}")
    if test_items:
        print("Run tests again to clean up")
EOF
```

## Unit Tests

**Run unit tests (no .env required):**
```bash
pytest tests/test_connection.py tests/test_models.py tests/test_exceptions.py -v
```

Unit tests cover:
- Connection configuration (8 tests)
- Data models (8 tests)
- Custom exceptions (6 tests)
- Environment variable loading (10 tests)

**Total unit tests: 32 tests**

## Running All Tests

```bash
# Run everything
pytest tests/ -v

# Run only unit tests
pytest tests/ -v -m "not integration"

# Run only integration tests
pytest tests/ -v -m integration

# Run with coverage
pytest tests/ --cov=storage_client --cov-report=html
```

## Test Results Summary

Current status:
```
Unit Tests:       32 passed ✅
Integration Tests: 15 passed, 4 skipped ⏭️
Total:            47 passed, 4 skipped
```

## Troubleshooting

### Integration tests skip with "No .env file found"
Create a `.env` file with your credentials.

### Authentication errors
- Check your API key/secret are correct
- Verify org/project IDs are correct
- Test with: `python debug_auth.py`

### "DataSource with id 0 not found"
Add to .env:
```bash
DEEPLYNX_DATA_SOURCE_ID=32
```

Or let the client auto-fetch the default.

### Tests fail with "Record not found"
This usually means cleanup from a previous run didn't complete. Run:
```bash
pytest tests/test_integration.py::test_cleanup_orphaned_items
```

## Writing New Tests

### Integration Test Template

```python
def test_my_feature(client, test_items):
    """Test description."""
    # Use client fixture for authenticated connection
    # Use test_items for pre-created test data

    result = client.items.create(ItemCreate(
        name="Test Item",
        description="Description",
        properties={
            "_test_suite_marker": TEST_MARKER,
            "_test_run_id": TEST_RUN_ID,
            "my_field": "value"
        }
    ))

    assert result is not None

    # Clean up
    client.items.delete(result.id)
```

### Unit Test Template

```python
def test_my_model():
    """Test model creation."""
    from storage_client import ItemCreate

    item = ItemCreate(
        name="Test",
        description="Test description",
        properties={"key": "value"}
    )

    assert item.name == "Test"
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run unit tests
        run: pytest tests/ -v -m "not integration"

      - name: Run integration tests
        if: github.event_name == 'push'
        env:
          DEEPLYNX_KEY: ${{ secrets.DEEPLYNX_KEY }}
          DEEPLYNX_SECRET: ${{ secrets.DEEPLYNX_SECRET }}
          DEEPLYNX_ORG_ID: 1
          DEEPLYNX_PROJECT_ID: 32
        run: pytest tests/test_integration.py -v
```

## Best Practices

1. **Always mark test items** with `_test_suite_marker`
2. **Clean up after tests** using fixtures or explicit deletion
3. **Use unique identifiers** like timestamps in test_run_id
4. **Skip tests gracefully** if features aren't configured
5. **Test both success and error cases**
6. **Keep tests independent** - don't rely on test order

## Quick Reference

```bash
# Quick verification
python test_connection.py

# Run integration tests
pytest tests/test_integration.py -v

# Run all tests
pytest tests/ -v

# List available data sources
python list_datasources.py

# Debug authentication
python debug_auth.py
```
