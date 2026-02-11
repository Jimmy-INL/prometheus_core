"""Basic usage example for the storage client library."""

from storage_client import StorageClient, ConnectionConfig, ItemCreate
from pathlib import Path

def main():
    # Configure connection
    config = ConnectionConfig(
        organization_id=123,  # Replace with your organization ID
        project_id=456,       # Replace with your project ID
        api_key="your-api-key",
        api_secret="your-api-secret"
    )

    # Use the synchronous client
    with StorageClient(config) as client:
        print("=== Creating an item ===")
        item = client.items.create(ItemCreate(
            name="Example Item",
            description="This is an example item",
            properties={
                "experiment_id": "EXP-001",
                "status": "active",
                "temperature": 298.15,
                "pressure": 101.325
            },
            tags=["example", "test", "2024"]
        ))
        print(f"Created item with ID: {item.id}")
        print(f"Name: {item.name}")
        print(f"Properties: {item.properties}")
        print(f"Tags: {[tag.name for tag in item.tags]}")

        print("\n=== Listing items ===")
        page = client.items.list(page=1, page_size=10)
        print(f"Found {page.page_info.total_count} total items")
        for i, item in enumerate(page.items, 1):
            print(f"{i}. {item.name} (ID: {item.id})")

        print("\n=== Searching by tags ===")
        results = client.search.by_tags(["example"], page_size=5)
        print(f"Found {len(results.items)} items with 'example' tag")
        for item in results.items:
            print(f"  - {item.name}")

        print("\n=== Updating an item ===")
        from storage_client import ItemUpdate
        updated = client.items.update(
            item_id=item.id,
            update=ItemUpdate(
                properties={
                    **item.properties,
                    "status": "completed"
                }
            )
        )
        print(f"Updated item {updated.id}: status = {updated.properties.get('status')}")

        print("\n=== Creating relationships ===")
        # Create another item
        item2 = client.items.create(ItemCreate(
            name="Related Item",
            properties={"type": "measurement"}
        ))

        # Create relationship
        from storage_client import RelationshipCreate
        rel = client.relationships.create(RelationshipCreate(
            from_item_id=item.id,
            to_item_id=item2.id,
            relationship_type="related_to",
            properties={"relationship_strength": "high"}
        ))
        print(f"Created relationship: {item.name} -> {item2.name}")

        print("\n=== Getting item relationships ===")
        relationships = client.relationships.get_item_relationships(item.id)
        print(f"Item {item.id} has {len(relationships)} relationships")

        print("\nExample completed successfully!")


if __name__ == "__main__":
    main()
