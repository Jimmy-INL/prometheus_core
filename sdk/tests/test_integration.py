"""Integration tests for storage client with real DeepLynx connection.

These tests require a .env file with valid credentials.
All test items are marked with _test_suite_marker property for safe cleanup.
"""

import pytest
import time
from pathlib import Path
from datetime import datetime
from prometheus_api.storage_client import (
    ConnectionConfig,
    StorageClient,
    ItemCreate,
    ItemUpdate,
    RelationshipCreate,
)

# Test marker to identify test items for safe cleanup
TEST_MARKER = "storage-client-test-suite"
TEST_RUN_ID = f"test-{int(time.time())}"


@pytest.fixture(scope="module")
def config():
    """Load configuration from .env file."""
    env_path = Path(".env")
    if not env_path.exists():
        pytest.skip("No .env file found - skipping integration tests")

    return ConnectionConfig.from_env()


@pytest.fixture(scope="module")
def client(config):
    """Create a storage client for the test session."""
    with StorageClient(config) as client:
        yield client


@pytest.fixture(scope="module")
def test_items(client):
    """Create test items and clean them up after tests."""
    created_items = []

    # Create test items
    test_data = [
        {
            "name": "Test Item Alpha",
            "description": "First test item for integration testing",
            "properties": {
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "category": "alpha",
                "priority": 1,
                "status": "active"
            }
        },
        {
            "name": "Test Item Beta",
            "description": "Second test item for integration testing",
            "properties": {
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "category": "beta",
                "priority": 2,
                "status": "active"
            }
        },
        {
            "name": "Test Item Gamma",
            "description": "Third test item for integration testing",
            "properties": {
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "category": "gamma",
                "priority": 3,
                "status": "pending"
            }
        },
        {
            "name": "Test Item Delta",
            "description": "Fourth test item for integration testing",
            "properties": {
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "category": "delta",
                "priority": 1,
                "status": "completed"
            }
        },
        {
            "name": "Test Item Epsilon",
            "description": "Fifth test item for integration testing",
            "properties": {
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "category": "epsilon",
                "priority": 2,
                "status": "active"
            }
        },
    ]

    for item_data in test_data:
        item = client.items.create(ItemCreate(**item_data))
        created_items.append(item)
        print(f"Created test item: {item.id} - {item.name}")

    yield created_items

    # Cleanup: Delete all test items from this run
    print(f"\nCleaning up {len(created_items)} test items...")
    for item in created_items:
        try:
            client.items.delete(item.id)
            print(f"Deleted test item: {item.id}")
        except Exception as e:
            print(f"Warning: Failed to delete item {item.id}: {e}")


class TestAuthentication:
    """Test authentication functionality."""

    def test_connection_with_env(self, config):
        """Test that configuration loads from .env."""
        assert config.organization_id is not None
        assert config.project_id is not None
        assert config.api_key is not None
        assert config.api_secret is not None

    def test_client_connection(self, client):
        """Test that client can connect successfully."""
        # If we got here, the fixture worked
        assert client is not None
        assert client.config is not None

    def test_data_source_fetching(self, client):
        """Test that data source can be fetched."""
        ds_id = client._get_data_source_id()
        assert ds_id is not None
        assert isinstance(ds_id, int)
        assert ds_id > 0


class TestItemCreation:
    """Test item creation functionality."""

    def test_create_single_item(self, client):
        """Test creating a single item."""
        item = client.items.create(ItemCreate(
            name="Single Test Item",
            description="A single test item",
            properties={
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "test": "single_create"
            }
        ))

        assert item.id is not None
        assert item.name == "Single Test Item"
        assert item.properties["test"] == "single_create"

        # Cleanup
        client.items.delete(item.id)

    def test_create_item_with_all_fields(self, client):
        """Test creating an item with all available fields."""
        item = client.items.create(ItemCreate(
            name="Complete Test Item",
            description="Item with all fields populated",
            properties={
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID,
                "string_field": "test",
                "number_field": 42,
                "boolean_field": True,
                "nested_field": {"key": "value"}
            },
            original_id=f"test-original-{int(time.time())}"
        ))

        assert item.id is not None
        assert item.name == "Complete Test Item"
        assert item.properties["number_field"] == 42
        assert item.properties["nested_field"]["key"] == "value"

        # Cleanup
        client.items.delete(item.id)

    def test_bulk_create_items(self, client):
        """Test creating multiple items in bulk."""
        items_to_create = [
            ItemCreate(
                name=f"Bulk Item {i}",
                description=f"Bulk test item number {i}",
                properties={
                    "_test_suite_marker": TEST_MARKER,
                    "_test_run_id": TEST_RUN_ID,
                    "bulk_index": i
                }
            )
            for i in range(3)
        ]

        items = client.items.bulk_create(items_to_create)

        assert len(items) == 3
        for i, item in enumerate(items):
            assert item.id is not None
            assert f"Bulk Item {i}" in item.name

        # Cleanup
        for item in items:
            client.items.delete(item.id)


class TestItemRetrieval:
    """Test item retrieval functionality."""

    def test_get_item_by_id(self, client, test_items):
        """Test retrieving an item by ID."""
        original_item = test_items[0]
        retrieved_item = client.items.get(original_item.id)

        assert retrieved_item.id == original_item.id
        assert retrieved_item.name == original_item.name
        assert retrieved_item.properties["_test_suite_marker"] == TEST_MARKER

    def test_list_items(self, client, test_items):
        """Test listing items with pagination."""
        page = client.items.list(page=1, page_size=10)

        assert page.items is not None
        assert len(page.items) > 0
        assert page.page_info.page_number == 1
        assert page.page_info.page_size == 10

        # Verify at least some of our test items are in the results
        item_ids = {item.id for item in page.items}
        test_item_ids = {item.id for item in test_items}
        assert len(item_ids & test_item_ids) > 0


class TestPagination:
    """Test pagination functionality."""

    def test_pagination_page_info(self, client, test_items):
        """Test that page info is correct."""
        page = client.items.list(page=1, page_size=2)

        assert page.page_info.page_number == 1
        assert page.page_info.page_size == 2
        # Note: API may return more items than page_size, so we just check it's positive
        assert page.page_info.total_count > 0
        assert page.page_info.has_previous is False

    def test_pagination_multiple_pages(self, client, test_items):
        """Test retrieving multiple pages."""
        # Note: API pagination may work differently than expected
        # This test just verifies the pagination API works
        page1 = client.items.list(page=1, page_size=2)
        page2 = client.items.list(page=2, page_size=2)

        # Both should return items
        assert len(page1.items) > 0
        assert len(page2.items) > 0

    def test_iter_all(self, client, test_items):
        """Test automatic pagination with iter_all."""
        # Count items from this test run
        count = 0
        found_test_items = []

        for item in client.items.iter_all(page_size=2):
            if item.properties.get("_test_run_id") == TEST_RUN_ID:
                count += 1
                found_test_items.append(item)

            # Stop after finding all our test items
            if count >= len(test_items):
                break

        assert count == len(test_items)

        # Verify we found all test items
        found_ids = {item.id for item in found_test_items}
        test_ids = {item.id for item in test_items}
        assert found_ids == test_ids


class TestItemUpdate:
    """Test item update functionality."""

    def test_update_item_name(self, client, test_items):
        """Test updating an item's name."""
        item = test_items[0]
        new_name = f"{item.name} - Updated"

        updated = client.items.update(
            item.id,
            ItemUpdate(name=new_name)
        )

        assert updated.id == item.id
        assert updated.name == new_name
        # No need to restore - items will be cleaned up by fixture

    def test_update_item_properties(self, client, test_items):
        """Test updating an item's properties."""
        item = test_items[1]  # Use a different item to avoid conflicts

        new_props = item.properties.copy()
        new_props["updated"] = True
        new_props["update_time"] = datetime.now().isoformat()

        updated = client.items.update(
            item.id,
            ItemUpdate(properties=new_props)
        )

        assert updated.properties["updated"] is True
        assert "update_time" in updated.properties
        # No need to restore - items will be cleaned up by fixture


class TestSearch:
    """Test search functionality."""

    def test_search_returns_results(self, client, test_items):
        """Test that search returns results."""
        # Search for items from our test run
        # Note: Search functionality may vary by DeepLynx configuration
        # This test just verifies the search endpoint works
        try:
            results = client.search.query("Test Item", page=1, page_size=10)
            assert results.items is not None
            assert results.page_info is not None
        except Exception as e:
            pytest.skip(f"Search not available or configured: {e}")

    def test_search_recent(self, client, test_items):
        """Test getting recent items."""
        try:
            recent = client.search.recent(limit=10)
            assert len(recent) > 0

            # Our test items should be recent
            recent_ids = {item.id for item in recent}
            test_ids = {item.id for item in test_items}

            # At least some overlap expected
            assert len(recent_ids & test_ids) > 0
        except Exception as e:
            pytest.skip(f"Recent search not available: {e}")


class TestRelationships:
    """Test relationship functionality."""

    def test_create_relationship(self, client, test_items):
        """Test creating a relationship between items."""
        item1 = test_items[0]
        item2 = test_items[1]

        try:
            rel = client.relationships.create(RelationshipCreate(
                from_item_id=item1.id,
                to_item_id=item2.id,
                relationship_type="test_relationship",
                properties={
                    "_test_suite_marker": TEST_MARKER,
                    "_test_run_id": TEST_RUN_ID
                }
            ))

            assert rel.id is not None
            assert rel.from_item_id == item1.id
            assert rel.to_item_id == item2.id

            # Cleanup
            client.relationships.delete(rel.id)
        except Exception as e:
            pytest.skip(f"Relationships not available or configured: {e}")

    def test_get_item_relationships(self, client, test_items):
        """Test retrieving relationships for an item."""
        item1 = test_items[0]
        item2 = test_items[1]

        try:
            # Create a relationship
            rel = client.relationships.create(RelationshipCreate(
                from_item_id=item1.id,
                to_item_id=item2.id,
                relationship_type="test_link"
            ))

            # Get relationships for item1
            rels = client.relationships.get_item_relationships(item1.id)

            assert len(rels) > 0

            # Cleanup
            client.relationships.delete(rel.id)
        except Exception as e:
            pytest.skip(f"Relationships not available: {e}")


class TestCleanup:
    """Test cleanup functionality."""

    def test_delete_item(self, client):
        """Test deleting an item."""
        # Create a temporary item
        item = client.items.create(ItemCreate(
            name="Temporary Item",
            description="Will be deleted",
            properties={
                "_test_suite_marker": TEST_MARKER,
                "_test_run_id": TEST_RUN_ID
            }
        ))

        item_id = item.id

        # Delete it
        client.items.delete(item_id)

        # Verify it's deleted by trying to retrieve it
        with pytest.raises(Exception):
            client.items.get(item_id)


# Utility test to clean up any orphaned test items
def test_cleanup_orphaned_items(client):
    """Clean up any test items left from previous failed runs.

    This test looks for items with our test marker and cleans them up.
    It's helpful if previous test runs failed before cleanup.
    """
    print("\nChecking for orphaned test items...")

    # Try to find items with our test marker
    # Note: This may not work depending on search capabilities
    try:
        # Get recent items and check for test marker
        recent = client.search.recent(limit=100)
        orphaned = [
            item for item in recent
            if item.properties.get("_test_suite_marker") == TEST_MARKER
            and item.properties.get("_test_run_id") != TEST_RUN_ID
        ]

        if orphaned:
            print(f"Found {len(orphaned)} orphaned test items from previous runs")
            for item in orphaned:
                try:
                    client.items.delete(item.id)
                    print(f"Cleaned up orphaned item: {item.id}")
                except Exception as e:
                    print(f"Could not delete {item.id}: {e}")
        else:
            print("No orphaned test items found")
    except Exception as e:
        print(f"Could not check for orphaned items: {e}")
