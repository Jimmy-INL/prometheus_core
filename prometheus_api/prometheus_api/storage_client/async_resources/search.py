"""Async search resource."""

from typing import Any, Dict, List, Optional
from ..models.item import Item, Tag
from ..models.pagination import Page, PageInfo
from .base import AsyncBaseResource


class AsyncSearchResource(AsyncBaseResource):
    """Handles async search and query operations."""

    async def query(
        self,
        query: str,
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Perform a simple text search across items asynchronously."""
        params = {
            "query": query,
            "page": page,
            "limit": page_size,
        }

        response = await self._client._request(
            "GET",
            f"/organizations/{self._client.config.organization_id}/query",
            params=params
        )

        return self._parse_search_results(response.json(), page, page_size)

    async def advanced_query(
        self,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Perform an advanced search with structured filters asynchronously."""
        payload = {
            "filters": filters,
            "page": page,
            "limit": page_size,
        }

        response = await self._client._request(
            "POST",
            f"/organizations/{self._client.config.organization_id}/query/advanced",
            json=payload
        )

        return self._parse_search_results(response.json(), page, page_size)

    async def by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Search for items by tags asynchronously."""
        params = {
            "tags": ",".join(tags),
            "match_all": "true" if match_all else "false",
            "page": page,
            "limit": page_size,
        }

        response = await self._client._request(
            "GET",
            f"{self._base_path}/records/search/tags",
            params=params
        )

        return self._parse_search_results(response.json(), page, page_size)

    async def recent(self, limit: int = 100) -> List[Item]:
        """Get recently created or updated items asynchronously."""
        params = {
            "limit": limit,
            "sort_by": "updated_at",
            "sort_order": "desc",
        }

        response = await self._client._request(
            "GET",
            f"{self._base_path}/records",
            params=params
        )

        data = response.json()
        return [self._parse_item(item_data) for item_data in data.get("records", [])]

    def _parse_search_results(
        self,
        data: Dict[str, Any],
        page: int,
        page_size: int
    ) -> Page[Item]:
        """Parse search results into a Page object."""
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

    def _parse_item(self, data: Dict[str, Any]) -> Item:
        """Parse item data from search results."""
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
