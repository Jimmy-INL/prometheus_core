"""Async search resource."""

from typing import Any, Dict, List
from ..models.item import Item, Tag
from ..models.pagination import Page, PageInfo
from .base import AsyncBaseResource


class AsyncSearchResource(AsyncBaseResource):
    """Handles async search and query operations."""

    async def query(self, query: str, page: int = 1, page_size: int = 100) -> Page[Item]:
        """Perform a simple text search across items asynchronously."""
        params = {
            "userQuery": query,
            "projectIds": [self._client.config.project_id],
        }

        response = await self._client._request(
            "GET",
            f"/organizations/{self._client.config.organization_id}/query/records",
            params=params,
        )

        data = response.json()
        if isinstance(data, list):
            items = data
        else:
            items = data.get("records", [])

        return self._parse_search_results(items, page, page_size)

    async def advanced_query(
        self, filters: Dict[str, Any], page: int = 1, page_size: int = 100
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
            json=payload,
        )

        return self._parse_search_results(response.json(), page, page_size)

    async def by_tags(
        self, tags: List[str], match_all: bool = False, page: int = 1, page_size: int = 100
    ) -> Page[Item]:
        """Search for items by tags asynchronously."""
        params = {
            "tags": ",".join(tags),
            "match_all": "true" if match_all else "false",
            "page": page,
            "limit": page_size,
        }

        response = await self._client._request(
            "GET", f"{self._base_path}/records/search/tags", params=params
        )

        return self._parse_search_results(response.json(), page, page_size)

    async def recent(self, limit: int = 100) -> List[Item]:
        """Get recently created or updated items asynchronously."""
        params = {
            "limit": limit,
            "sort_by": "updated_at",
            "sort_order": "desc",
        }

        response = await self._client._request("GET", f"{self._base_path}/records", params=params)

        data = response.json()
        if isinstance(data, list):
            items = data
        else:
            items = data.get("records", [])
        return [self._parse_item(item_data) for item_data in items]

    def _parse_search_results(self, data: Any, page: int, page_size: int) -> Page[Item]:
        """Parse search results into a Page object."""
        if isinstance(data, list):
            item_list = data
            total_count = len(data)
        else:
            item_list = data.get("records", [])
            total_count = data.get("total", len(item_list))

        items = [self._parse_item(item_data) for item_data in item_list]

        page_info = PageInfo(
            page_number=page,
            page_size=page_size,
            total_count=total_count,
            has_next=page * page_size < total_count,
            has_previous=page > 1,
        )

        return Page(items=items, page_info=page_info)

    def _parse_item(self, data: Dict[str, Any]) -> Item:
        """Parse item data from search results."""
        import json as json_lib
        from datetime import datetime

        properties = data.get("properties", {})
        if isinstance(properties, str):
            try:
                properties = json_lib.loads(properties)
            except (TypeError, ValueError):
                properties = {}

        timestamp_str = data.get("lastUpdatedAt")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        tags_data = data.get("tags")
        tags = []
        if tags_data:
            if isinstance(tags_data, str):
                try:
                    tags_list = json_lib.loads(tags_data)
                    tags = [Tag(id=t.get("id"), name=t.get("name", "")) for t in tags_list]
                except (TypeError, ValueError):
                    tags = []
            elif isinstance(tags_data, list):
                tags = [Tag(id=t.get("id"), name=t.get("name", "")) for t in tags_data]

        return Item(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description"),
            properties=properties,
            class_id=data.get("classId"),
            original_id=data.get("originalId"),
            created_at=timestamp,
            updated_at=timestamp,
            tags=tags,
            metatype_id=data.get("classId"),
            metatype_name=data.get("className"),
            data_source_id=data.get("dataSourceId"),
        )
