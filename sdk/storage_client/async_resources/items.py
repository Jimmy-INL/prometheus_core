"""Async items resource."""

from typing import AsyncIterator, Dict, List, Optional, Any
from ..models.item import Item, ItemCreate, ItemUpdate, Tag
from ..models.pagination import Page, PageInfo
from .base import AsyncBaseResource


class AsyncItemsResource(AsyncBaseResource):
    """Handles async operations related to items."""

    async def create(self, item: ItemCreate) -> Item:
        """Create a new item asynchronously."""
        payload = {
            "name": item.name,
            "properties": item.properties,
        }

        if item.description:
            payload["description"] = item.description
        if item.class_id:
            payload["metatype_id"] = item.class_id
        if item.original_id:
            payload["original_data_id"] = item.original_id

        response = await self._client._request(
            "POST",
            f"{self._base_path}/records",
            json=payload
        )

        item_data = response.json()

        if item.tags:
            item_id = item_data.get("id")
            await self.add_tags(item_id, item.tags)
            return await self.get(item_id)

        return self._parse_item(item_data)

    async def get(self, item_id: int) -> Item:
        """Get an item by ID asynchronously."""
        response = await self._client._request(
            "GET",
            f"{self._base_path}/records/{item_id}"
        )

        return self._parse_item(response.json())

    async def update(self, item_id: int, update: ItemUpdate) -> Item:
        """Update an existing item asynchronously."""
        payload = {}

        if update.name is not None:
            payload["name"] = update.name
        if update.description is not None:
            payload["description"] = update.description
        if update.properties is not None:
            payload["properties"] = update.properties
        if update.class_id is not None:
            payload["metatype_id"] = update.class_id
        if update.original_id is not None:
            payload["original_data_id"] = update.original_id

        response = await self._client._request(
            "PATCH",
            f"{self._base_path}/records/{item_id}",
            json=payload
        )

        return self._parse_item(response.json())

    async def delete(self, item_id: int) -> None:
        """Delete an item asynchronously."""
        await self._client._request(
            "DELETE",
            f"{self._base_path}/records/{item_id}"
        )

    async def list(
        self,
        page: int = 1,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> Page[Item]:
        """List items with pagination asynchronously."""
        params = {
            "page": page,
            "limit": page_size,
        }

        if filters:
            params.update(filters)

        response = await self._client._request(
            "GET",
            f"{self._base_path}/records",
            params=params
        )

        data = response.json()
        items = [self._parse_item(item_data) for item_data in data.get("records", [])]

        total_count = data.get("total", len(items))
        page_info = PageInfo(
            page_number=page,
            page_size=page_size,
            total_count=total_count,
            has_next=page * page_size < total_count,
            has_previous=page > 1
        )

        return Page(items=items, page_info=page_info)

    async def iter_all(
        self,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Item]:
        """Iterate over all items with automatic pagination asynchronously."""
        page = 1
        while True:
            result = await self.list(page=page, page_size=page_size, filters=filters)
            for item in result.items:
                yield item

            if not result.page_info.has_next:
                break

            page += 1

    async def bulk_create(self, items: List[ItemCreate]) -> List[Item]:
        """Create multiple items in a single request asynchronously."""
        payload = [
            {
                "name": item.name,
                "description": item.description,
                "properties": item.properties,
                "metatype_id": item.class_id,
                "original_data_id": item.original_id,
            }
            for item in items
        ]

        response = await self._client._request(
            "POST",
            f"{self._base_path}/records/bulk",
            json=payload
        )

        data = response.json()
        return [self._parse_item(item_data) for item_data in data.get("records", [])]

    async def add_tags(self, item_id: int, tags: List[str]) -> Item:
        """Add tags to an item asynchronously."""
        response = await self._client._request(
            "POST",
            f"{self._base_path}/records/{item_id}/tags",
            json={"tags": tags}
        )

        return self._parse_item(response.json())

    async def remove_tags(self, item_id: int, tags: List[str]) -> Item:
        """Remove tags from an item asynchronously."""
        response = await self._client._request(
            "DELETE",
            f"{self._base_path}/records/{item_id}/tags",
            json={"tags": tags}
        )

        return self._parse_item(response.json())

    def _parse_item(self, data: Dict[str, Any]) -> Item:
        """Parse API response data into an Item model."""
        return Item(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description"),
            properties=data.get("properties", {}),
            class_id=data.get("metatype_id"),
            original_id=data.get("original_data_id"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            tags=[Tag(id=t.get("id"), name=t["name"]) for t in data.get("tags", [])],
            metatype_id=data.get("metatype_id"),
            metatype_name=data.get("metatype_name"),
            data_source_id=data.get("data_source_id"),
        )
