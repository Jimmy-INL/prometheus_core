"""Bulk operations example for the storage client library."""

from storage_client import (
    StorageClient,
    ConnectionConfig,
    ItemCreate,
    RelationshipCreate
)


def main():
    # Configure connection
    config = ConnectionConfig(
        organization_id=123,  # Replace with your organization ID
        project_id=456,       # Replace with your project ID
        api_key="your-api-key",
        api_secret="your-api-secret"
    )

    with StorageClient(config) as client:
        print("=== Bulk creating items ===")

        # Create many items at once
        items_to_create = [
            ItemCreate(
                name=f"Sensor {i:03d}",
                properties={
                    "sensor_id": f"S{i:03d}",
                    "type": "temperature" if i % 2 == 0 else "pressure",
                    "location": f"Zone {(i % 10) + 1}",
                    "status": "active"
                },
                tags=["sensor", "monitoring"]
            )
            for i in range(50)
        ]

        items = client.items.bulk_create(items_to_create)
        print(f"Created {len(items)} items in bulk")

        # Show first few
        for item in items[:5]:
            print(f"  - {item.name} (ID: {item.id})")
        print(f"  ... and {len(items) - 5} more")

        print("\n=== Bulk creating relationships ===")

        # Create a hub item
        hub = client.items.create(ItemCreate(
            name="Sensor Network Hub",
            properties={"type": "hub", "location": "Central"}
        ))
        print(f"Created hub: {hub.name} (ID: {hub.id})")

        # Create relationships from all sensors to the hub
        relationships_to_create = [
            RelationshipCreate(
                from_item_id=item.id,
                to_item_id=hub.id,
                relationship_type="reports_to",
                properties={"data_interval": "1min"}
            )
            for item in items
        ]

        relationships = client.relationships.bulk_create(relationships_to_create)
        print(f"Created {len(relationships)} relationships in bulk")

        print("\n=== Verifying relationships ===")
        hub_relationships = client.relationships.get_item_relationships(
            hub.id,
            direction="incoming"
        )
        print(f"Hub has {len(hub_relationships)} incoming relationships")

        print("\n=== Iterating over all items with filtering ===")
        # Process items in batches
        temperature_sensors = []
        for item in client.items.iter_all(page_size=20):
            if item.properties.get("type") == "temperature":
                temperature_sensors.append(item)

        print(f"Found {len(temperature_sensors)} temperature sensors")

        print("\n=== Bulk tagging ===")
        # Add additional tags to all temperature sensors
        for sensor in temperature_sensors[:5]:  # Just first 5 for demo
            client.items.add_tags(sensor.id, ["temperature", "climate-control"])
            print(f"Tagged {sensor.name}")

        print("\n=== Pagination through large result sets ===")
        page_num = 1
        while True:
            page = client.items.list(page=page_num, page_size=10)
            print(f"Page {page_num}: {len(page.items)} items")

            if not page.page_info.has_next:
                break

            page_num += 1
            if page_num > 3:  # Limit for demo
                print("  (stopping after 3 pages)")
                break

        print("\n=== Search across all created items ===")
        results = client.search.by_tags(["sensor"], page_size=100)
        print(f"Found {len(results.items)} items with 'sensor' tag")

        # Group by type
        by_type = {}
        for item in results.items:
            item_type = item.properties.get("type", "unknown")
            by_type[item_type] = by_type.get(item_type, 0) + 1

        print("Breakdown by type:")
        for item_type, count in by_type.items():
            print(f"  {item_type}: {count}")

        print("\nBulk operations example completed successfully!")


if __name__ == "__main__":
    main()
