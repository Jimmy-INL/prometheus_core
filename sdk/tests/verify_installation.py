#!/usr/bin/env python
"""Verification script for storage client library installation."""

import sys


def test_imports():
    """Test that all main components can be imported."""
    print("Testing imports...")

    try:
        # Core imports
        from prometheus_api.storage_client import (  # noqa: F401
            StorageClient,
            AsyncStorageClient,
            ConnectionConfig,
        )
        print("✓ Core clients imported successfully")

        # Model imports
        from prometheus_api.storage_client import (  # noqa: F401
            Item,
            ItemCreate,
            ItemUpdate,
            FileMetadata,
            FileUpload,
            Relationship,
            RelationshipCreate,
            Page,
            PageInfo,
            Tag,
        )
        print("✓ Data models imported successfully")

        # Exception imports
        from prometheus_api.storage_client import (  # noqa: F401
            StorageClientError,
            AuthenticationError,
            ItemNotFoundError,
            ValidationError,
            APIError,
        )
        print("✓ Exception classes imported successfully")

        return True

    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_configuration():
    """Test creating configuration objects."""
    print("\nTesting configuration...")

    try:
        from prometheus_api.storage_client import ConnectionConfig

        # Test API key auth
        config1 = ConnectionConfig(
            organization_id=123,
            project_id=456,
            api_key="test-key",
            api_secret="test-secret"
        )
        assert config1.uses_api_key is True
        assert config1.uses_jwt is False
        print("✓ API key configuration created successfully")

        # Test JWT auth
        config2 = ConnectionConfig(
            organization_id=123,
            project_id=456,
            jwt_token="test-token"
        )
        assert config2.uses_jwt is True
        assert config2.uses_api_key is False
        print("✓ JWT configuration created successfully")

        # Test immutability
        try:
            config1.organization_id = 999
            print("✗ Configuration is not immutable")
            return False
        except Exception:
            print("✓ Configuration is immutable")

        return True

    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def test_models():
    """Test creating model instances."""
    print("\nTesting models...")

    try:
        from prometheus_api.storage_client import ItemCreate, ItemUpdate, RelationshipCreate
        from prometheus_api.storage_client.models.pagination import PageInfo

        # Test ItemCreate
        item = ItemCreate(
            name="Test Item",
            description="Test description",
            properties={"key": "value"},
            tags=["tag1", "tag2"]
        )
        assert item.name == "Test Item"
        assert item.properties == {"key": "value"}
        print("✓ ItemCreate model works correctly")

        # Test ItemUpdate
        update = ItemUpdate(name="Updated Name")
        assert update.name == "Updated Name"
        assert update.description is None
        print("✓ ItemUpdate model works correctly")

        # Test RelationshipCreate
        rel = RelationshipCreate(
            from_item_id=1,
            to_item_id=2,
            relationship_type="related_to"
        )
        assert rel.from_item_id == 1
        assert rel.to_item_id == 2
        print("✓ RelationshipCreate model works correctly")

        # Test PageInfo
        page_info = PageInfo(
            page_number=2,
            page_size=10,
            total_count=45,
            has_next=True,
            has_previous=True
        )
        assert page_info.total_pages == 5
        print("✓ PageInfo model works correctly")

        return True

    except Exception as e:
        print(f"✗ Model test failed: {e}")
        return False


def test_exceptions():
    """Test exception classes."""
    print("\nTesting exceptions...")

    try:
        from prometheus_api.storage_client.exceptions import (
            ItemNotFoundError,
            ValidationError,
            APIError
        )

        # Test ItemNotFoundError
        error = ItemNotFoundError(item_id=123)
        assert error.item_id == 123
        print("✓ ItemNotFoundError works correctly")

        # Test ValidationError
        error = ValidationError("Invalid input", details={"field": "name"})
        assert error.details == {"field": "name"}
        print("✓ ValidationError works correctly")

        # Test APIError
        error = APIError("Server error", status_code=500)
        assert error.status_code == 500
        print("✓ APIError works correctly")

        return True

    except Exception as e:
        print(f"✗ Exception test failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Storage Client Library - Installation Verification")
    print("=" * 60)

    tests = [
        test_imports,
        test_configuration,
        test_models,
        test_exceptions,
    ]

    results = []
    for test in tests:
        result = test()
        results.append(result)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if all(results):
        print("\n✓ All verification tests passed!")
        print("\nThe storage client library is installed correctly.")
        print("You can now use it in your applications.")
        return 0
    else:
        print("\n✗ Some verification tests failed.")
        print("Please check the error messages above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
