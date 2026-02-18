"""Search resource for synchronous operations."""

from typing import Any, Dict, List, Optional
from ..models.item import Item
from ..models.pagination import Page, PageInfo
from .base import BaseResource


class SearchResource(BaseResource):
    """Handles search and query operations."""

    def query(
        self,
        query: str,
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Perform a simple text search across items.

        Args:
            query: Search query string
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated search results

        Example:
            ```python
            results = client.search.query("experiment data", page_size=50)
            for item in results.items:
                print(item.name)
            ```
        """
        params = {
            "query": query,
            "page": page,
            "limit": page_size,
        }

        response = self._client._request(
            "GET",
            f"/organizations/{self._client.config.organization_id}/query",
            params=params
        )

        return self._parse_search_results(response.json(), page, page_size)

    def advanced_query(
        self,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Perform an advanced search with structured filters.

        Args:
            filters: Dictionary of filter criteria
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated search results

        Example:
            ```python
            results = client.search.advanced_query({
                "properties.status": "active",
                "properties.priority": {"$gt": 5}
            })
            ```
        """
        payload = {
            "filters": filters,
            "page": page,
            "limit": page_size,
        }

        response = self._client._request(
            "POST",
            f"/organizations/{self._client.config.organization_id}/query/advanced",
            json=payload
        )

        return self._parse_search_results(response.json(), page, page_size)

    def by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        page: int = 1,
        page_size: int = 100
    ) -> Page[Item]:
        """Search for items by tags.

        Args:
            tags: List of tag names to search for
            match_all: If True, items must have all tags; if False, any tag matches
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            Paginated search results

        Example:
            ```python
            # Find items with any of these tags
            results = client.search.by_tags(["important", "urgent"])

            # Find items with all of these tags
            results = client.search.by_tags(["important", "urgent"], match_all=True)
            ```
        """
        params = {
            "tags": ",".join(tags),
            "match_all": "true" if match_all else "false",
            "page": page,
            "limit": page_size,
        }

        response = self._client._request(
            "GET",
            f"{self._base_path}/records/search/tags",
            params=params
        )

        return self._parse_search_results(response.json(), page, page_size)

    def recent(self, limit: int = 100) -> List[Item]:
        """Get recently created or updated items.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of recent items

        Example:
            ```python
            recent_items = client.search.recent(limit=50)
            ```
        """
        params = {
            "limit": limit,
            "sort_by": "updated_at",
            "sort_order": "desc",
        }

        response = self._client._request(
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
        """Parse search results into a Page object.

        Args:
            data: Raw API response data
            page: Current page number
            page_size: Page size

        Returns:
            Paginated results
        """
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
        """Parse item data from search results.

        Args:
            data: Raw item data

        Returns:
            Parsed Item object
        """
        from ..models.item import Tag

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
