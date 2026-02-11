# Storage Client Library

A full-featured Python client library that provides a clean, generic interface for storage operations. The library abstracts backend implementation details and offers both synchronous and asynchronous APIs.

## Features

- **Generic Terminology**: Uses intuitive terms like `Item`, `Relationship`, `Metadata` instead of backend-specific terminology
- **Dual API Support**: Both synchronous and asynchronous clients using httpx
- **Type Safety**: Fully typed with Pydantic models for validation and IDE support
- **Full Feature Set**:
  - CRUD operations for items
  - File upload/download (including chunked uploads for large files)
  - Relationship management
  - Search and query capabilities
  - Timeseries data support
  - Bulk operations
  - Automatic pagination
  - Tag management

## Installation

```bash
pip install -r requirements.txt
```

Or install in development mode:

```bash
pip install -e .
```

## Quick Start

### Synchronous Usage

```python
from storage_client import StorageClient, ConnectionConfig, ItemCreate
from pathlib import Path

# Configure connection
config = ConnectionConfig(
    organization_id=123,
    project_id=456,
    api_key="your-api-key",
    api_secret="your-api-secret"
)

# Use the client
with StorageClient(config) as client:
    # Create an item
    item = client.items.create(ItemCreate(
        name="Experiment Results",
        properties={
            "experiment_id": "EXP-001",
            "status": "completed",
            "temperature": 298.15
        },
        tags=["important", "2024"]
    ))
    print(f"Created item: {item.id}")

    # Upload a file
    file_meta = client.files.upload(
        Path("data.csv"),
        description="Experimental data"
    )

    # Create a relationship
    client.relationships.create(RelationshipCreate(
        from_item_id=item.id,
        to_item_id=file_meta.id,
        relationship_type="has_attachment"
    ))

    # Search by tags
    results = client.search.by_tags(["important"])
    for result in results.items:
        print(f"Found: {result.name}")
```

### Asynchronous Usage

```python
import asyncio
from storage_client import AsyncStorageClient, ConnectionConfig, ItemCreate

async def main():
    config = ConnectionConfig(
        organization_id=123,
        project_id=456,
        api_key="your-api-key",
        api_secret="your-api-secret"
    )

    async with AsyncStorageClient(config) as client:
        # Create items
        item = await client.items.create(ItemCreate(
            name="Async Item",
            properties={"key": "value"}
        ))

        # List items with pagination
        page = await client.items.list(page=1, page_size=50)
        for item in page.items:
            print(f"Item: {item.name}")

        # Iterate over all items automatically
        async for item in client.items.iter_all(page_size=100):
            print(f"Processing: {item.name}")

asyncio.run(main())
```

## Configuration

The `ConnectionConfig` class supports multiple configuration options:

```python
from storage_client import ConnectionConfig

# Using API key authentication
config = ConnectionConfig(
    organization_id=123,
    project_id=456,
    api_key="your-api-key",
    api_secret="your-api-secret",
    base_url="https://api.example.com",  # Optional, has default
    timeout=30.0,  # Request timeout in seconds
    max_retries=3,  # Number of retry attempts
    verify_ssl=True  # SSL certificate verification
)

# Using JWT token authentication
config = ConnectionConfig(
    organization_id=123,
    project_id=456,
    jwt_token="your-jwt-token"
)
```

## API Reference

### Items Operations

```python
# Create a single item
item = client.items.create(ItemCreate(name="Test", properties={"key": "value"}))

# Get an item by ID
item = client.items.get(item_id=123)

# Update an item
updated = client.items.update(item_id=123, update=ItemUpdate(name="New Name"))

# Delete an item
client.items.delete(item_id=123)

# List items with pagination
page = client.items.list(page=1, page_size=100)

# Iterate over all items (automatic pagination)
for item in client.items.iter_all():
    print(item.name)

# Bulk create items
items = client.items.bulk_create([
    ItemCreate(name="Item 1"),
    ItemCreate(name="Item 2")
])

# Manage tags
item = client.items.add_tags(item_id=123, tags=["important", "reviewed"])
item = client.items.remove_tags(item_id=123, tags=["old-tag"])
```

### File Operations

```python
from pathlib import Path

# Upload a file
file_meta = client.files.upload(
    Path("data.csv"),
    description="Experiment data"
)

# Upload a large file in chunks
file_meta = client.files.upload_chunked(
    Path("large_file.zip"),
    chunk_size=10 * 1024 * 1024  # 10MB chunks
)

# Get file metadata
file_meta = client.files.get(file_id=123)

# Download a file
client.files.download(file_id=123, output_path=Path("downloaded.csv"))

# Delete a file
client.files.delete(file_id=123)
```

### Relationship Operations

```python
# Create a relationship
rel = client.relationships.create(RelationshipCreate(
    from_item_id=1,
    to_item_id=2,
    relationship_type="depends_on",
    properties={"strength": "high"}
))

# Get a relationship
rel = client.relationships.get(relationship_id=123)

# Delete a relationship
client.relationships.delete(relationship_id=123)

# Bulk create relationships
rels = client.relationships.bulk_create([
    RelationshipCreate(from_item_id=1, to_item_id=2, relationship_type="links"),
    RelationshipCreate(from_item_id=2, to_item_id=3, relationship_type="links")
])

# Get all relationships for an item
all_rels = client.relationships.get_item_relationships(item_id=123)
outgoing = client.relationships.get_item_relationships(item_id=123, direction="outgoing")

# Get relationship graph
graph = client.relationships.get_item_graph(item_id=123, depth=2)
```

### Search Operations

```python
# Simple text search
results = client.search.query("experiment data", page_size=50)

# Advanced search with filters
results = client.search.advanced_query({
    "properties.status": "active",
    "properties.priority": {"$gt": 5}
})

# Search by tags
results = client.search.by_tags(["important", "urgent"])
results = client.search.by_tags(["tag1", "tag2"], match_all=True)

# Get recent items
recent = client.search.recent(limit=50)
```

### Timeseries Operations

```python
from pathlib import Path

# Upload timeseries data
result = client.timeseries.upload(
    Path("sensor_data.csv"),
    data_source_id=456
)

# Query timeseries data
results = client.timeseries.query(
    data_source_id=456,
    sql_query="SELECT * FROM data WHERE timestamp > '2024-01-01'",
    file_type="json"
)
```

## Error Handling

The library provides custom exceptions for different error scenarios:

```python
from storage_client.exceptions import (
    StorageClientError,      # Base exception
    AuthenticationError,     # Authentication failures
    ItemNotFoundError,       # Item not found (404)
    ValidationError,         # Validation errors (4xx)
    APIError                 # Other API errors (5xx)
)

try:
    item = client.items.get(item_id=999)
except ItemNotFoundError as e:
    print(f"Item {e.item_id} not found")
except AuthenticationError:
    print("Authentication failed")
except APIError as e:
    print(f"API error {e.status_code}: {e.message}")
```

## Advanced Usage

### Pagination

```python
# Manual pagination
page = client.items.list(page=1, page_size=50)
print(f"Page {page.page_info.page_number} of {page.page_info.total_pages}")
print(f"Total items: {page.page_info.total_count}")

if page.page_info.has_next:
    next_page = client.items.list(page=2, page_size=50)

# Automatic pagination
for item in client.items.iter_all(page_size=100):
    # Process each item across all pages
    process(item)
```

### Filtering

```python
# Filter items in list operation
results = client.items.list(
    page=1,
    page_size=100,
    filters={
        "properties.status": "active",
        "created_at": {"$gt": "2024-01-01"}
    }
)
```

### Bulk Operations

```python
# Create multiple items efficiently
items = client.items.bulk_create([
    ItemCreate(name=f"Item {i}", properties={"index": i})
    for i in range(100)
])

# Create multiple relationships
relationships = client.relationships.bulk_create([
    RelationshipCreate(
        from_item_id=items[i].id,
        to_item_id=items[i+1].id,
        relationship_type="next"
    )
    for i in range(len(items) - 1)
])
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

### Code Quality

```bash
# Format code
black storage_client/

# Lint
ruff check storage_client/

# Type checking
mypy storage_client/
```

## Architecture

The library is organized into several key components:

- **Client Layer** (`client.py`, `async_client.py`): Main entry points with context manager support
- **Resource Layer** (`resources/`, `async_resources/`): Organized API operations by domain
- **Models Layer** (`models/`): Pydantic data models for type safety and validation
- **Auth Layer** (`auth.py`): Automatic JWT token management and refresh
- **Utilities** (`utils/`): Helper functions for pagination, streaming, etc.

All backend-specific terminology and identifiers are hidden from the public API, providing a clean, generic interface.

## License

MIT License

## Support

For issues and questions, please contact your system administrator or refer to the internal documentation.
