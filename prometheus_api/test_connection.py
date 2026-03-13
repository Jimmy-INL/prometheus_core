#!/usr/bin/env python
"""Test script to verify connection and basic operations."""

from prometheus_api.storage_client import ConnectionConfig, StorageClient, ItemCreate
from pathlib import Path

def main():
    print("=" * 70)
    print("Testing Storage Client Connection")
    print("=" * 70)
    print()

    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ No .env file found!")
        print()
        print("Please create a .env file with your credentials:")
        print("  cp .env.example .env")
        print("  vim .env")
        print()
        return 1

    try:
        # Load configuration from .env file
        print("Loading configuration from .env...")
        config = ConnectionConfig.from_env()
        print(f"✓ Configuration loaded")
        print(f"  Organization: {config.organization_id}")
        print(f"  Project: {config.project_id}")
        print()

        # Connect to the storage backend
        print("Connecting to storage backend...")
        with StorageClient(config) as client:
            print("✓ Connected successfully")
            print()

            # Create a test item
            print("Creating test item...")
            test_item = ItemCreate(
                name="Test Item from Python",
                description="This is a test item created to verify the connection",
                properties={
                    "test": True,
                    "source": "test_connection.py",
                    "message": "Hello from the storage client!"
                }
                # Note: Tags removed for now - will implement proper tag handling
            )

            created_item = client.items.create(test_item)
            print(f"✓ Item created successfully!")
            print(f"  ID: {created_item.id}")
            print(f"  Name: {created_item.name}")
            print(f"  Description: {created_item.description}")
            print(f"  Properties: {created_item.properties}")
            print(f"  Tags: {[tag.name for tag in created_item.tags]}")
            print()

            # Retrieve the item to verify
            print("Retrieving the item...")
            retrieved_item = client.items.get(created_item.id)
            print(f"✓ Item retrieved successfully!")
            print(f"  ID: {retrieved_item.id}")
            print(f"  Name: {retrieved_item.name}")
            print(f"  Message: {retrieved_item.properties.get('message')}")
            print()

            # Verify the data matches
            assert created_item.id == retrieved_item.id
            assert created_item.name == retrieved_item.name
            assert created_item.properties == retrieved_item.properties
            print("✓ Data verification passed!")
            print()

            # Clean up - delete the test item
            print("Cleaning up test item...")
            client.items.delete(created_item.id)
            print("✓ Test item deleted")
            print()

        print("=" * 70)
        print("✅ All tests passed successfully!")
        print("=" * 70)
        print()
        print("Your storage client is working correctly!")
        print("You can now use it in your applications.")
        return 0

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print()
        print("Make sure your .env file contains:")
        print("  DEEPLYNX_KEY")
        print("  DEEPLYNX_SECRET")
        print("  DEEPLYNX_ORG_ID")
        print("  DEEPLYNX_PROJECT_ID")
        return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print(f"Error type: {type(e).__name__}")
        if hasattr(e, 'status_code'):
            print(f"Status code: {e.status_code}")
        if hasattr(e, 'response_data'):
            print(f"Response: {e.response_data}")
        return 1


if __name__ == "__main__":
    exit(main())
