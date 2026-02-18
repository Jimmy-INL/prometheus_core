"""Asynchronous usage example for the storage client library."""

import asyncio
from prometheus_api.storage_client import AsyncStorageClient, ConnectionConfig, ItemCreate


async def main():
    # Configure connection from .env file
    config = ConnectionConfig.from_env()

    # Use the asynchronous client
    async with AsyncStorageClient(config) as client:
        print("=== Creating items asynchronously ===")

        # Create multiple items concurrently
        items_to_create = [
            ItemCreate(
                name=f"Async Item {i}",
                description=f"Async test item number {i}",
                properties={
                    "index": i,
                    "batch": "async-demo",
                    "_example_script": True
                }
            )
            for i in range(5)
        ]

        # Use bulk create for efficiency
        items = await client.items.bulk_create(items_to_create)
        print(f"Created {len(items)} items")
        for item in items:
            print(f"  - {item.name} (ID: {item.id})")

        print("\n=== Iterating over all items ===")
        count = 0
        async for item in client.items.iter_all(page_size=10):
            count += 1
            if count <= 5:  # Print first 5
                print(f"{count}. {item.name}")
            elif count == 6:
                print("  ...")
        print(f"Total items iterated: {count}")

        print("\n=== Concurrent operations ===")
        # Perform multiple operations concurrently
        tasks = [
            client.search.query("async"),
            client.search.by_tags(["example"]),
            client.items.list(page=1, page_size=5)
        ]

        results = await asyncio.gather(*tasks)
        print(f"Query results: {len(results[0].items)} items")
        print(f"Tag search results: {len(results[1].items)} items")
        print(f"List results: {len(results[2].items)} items")

        print("\n=== Cleaning up (optional) ===")
        # Delete the items we created
        for item in items:
            await client.items.delete(item.id)
            print(f"Deleted item {item.id}")

        print("\nAsync example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
