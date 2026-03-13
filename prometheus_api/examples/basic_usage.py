"""Basic usage example for the storage client library."""

from prometheus_api.storage_client import StorageClient, ConnectionConfig, ItemCreate, ItemUpdate

def main():
    # Configure connection from .env file
    # Make sure you have a .env file with:
    #   DEEPLYNX_KEY=...
    #   DEEPLYNX_SECRET=...
    #   DEEPLYNX_ORG_ID=...
    #   DEEPLYNX_PROJECT_ID=...
    config = ConnectionConfig.from_env()

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
                "pressure": 101.325,
                "_example_script": True  # Mark as from example script
            }
        ))
        print(f"Created item with ID: {item.id}")
        print(f"Name: {item.name}")
        print(f"Properties: {item.properties}")
        print(f"Created at: {item.created_at}")

        print("\n=== Listing items ===")
        page = client.items.list(page=1, page_size=10)
        print(f"Found {page.page_info.total_count} total items")
        for i, item in enumerate(page.items, 1):
            print(f"{i}. {item.name} (ID: {item.id})")

        print("\n=== Searching for recent items ===")
        try:
            recent = client.search.recent(limit=5)
            print(f"Found {len(recent)} recent items")
            for recent_item in recent[:3]:
                print(f"  - {recent_item.name} (ID: {recent_item.id})")
        except Exception as e:
            print(f"Search not available: {e}")

        print("\n=== Updating an item ===")
        updated = client.items.update(
            item_id=item.id,
            update=ItemUpdate(
                properties={
                    **item.properties,
                    "status": "completed",
                    "completion_time": "2026-02-11T12:00:00Z"
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
        from prometheus_api.storage_client import RelationshipCreate
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
