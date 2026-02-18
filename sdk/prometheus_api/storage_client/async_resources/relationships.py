"""Async relationships resource."""

from typing import Any, Dict, List, Optional
from ..models.relationship import Relationship, RelationshipCreate
from .base import AsyncBaseResource


class AsyncRelationshipsResource(AsyncBaseResource):
    """Handles async operations related to relationships between items."""

    async def create(self, relationship: RelationshipCreate) -> Relationship:
        """Create a new relationship between two items asynchronously."""
        payload = {
            "origin_id": relationship.from_item_id,
            "destination_id": relationship.to_item_id,
            "relationship_type": relationship.relationship_type,
            "properties": relationship.properties,
        }

        params = {
            "dataSourceId": await self._client._get_data_source_id()
        }

        response = await self._client._request(
            "POST",
            f"{self._base_path}/edges",
            json=payload,
            params=params
        )

        return self._parse_relationship(response.json())

    async def get(self, relationship_id: int) -> Relationship:
        """Get a relationship by ID asynchronously."""
        response = await self._client._request(
            "GET",
            f"{self._base_path}/edges/{relationship_id}"
        )

        return self._parse_relationship(response.json())

    async def delete(self, relationship_id: int) -> None:
        """Delete a relationship asynchronously."""
        await self._client._request(
            "DELETE",
            f"{self._base_path}/edges/{relationship_id}"
        )

    async def bulk_create(self, relationships: List[RelationshipCreate]) -> List[Relationship]:
        """Create multiple relationships in a single request asynchronously."""
        payload = [
            {
                "origin_id": rel.from_item_id,
                "destination_id": rel.to_item_id,
                "relationship_type": rel.relationship_type,
                "properties": rel.properties,
            }
            for rel in relationships
        ]

        params = {
            "dataSourceId": await self._client._get_data_source_id()
        }

        response = await self._client._request(
            "POST",
            f"{self._base_path}/edges/bulk",
            json=payload,
            params=params
        )

        data = response.json()
        return [self._parse_relationship(rel_data) for rel_data in data.get("edges", [])]

    async def get_item_relationships(
        self,
        item_id: int,
        direction: Optional[str] = None
    ) -> List[Relationship]:
        """Get all relationships for an item asynchronously."""
        params = {}
        if direction:
            params["direction"] = direction

        response = await self._client._request(
            "GET",
            f"{self._base_path}/records/{item_id}/edges",
            params=params
        )

        data = response.json()
        return [self._parse_relationship(rel_data) for rel_data in data.get("edges", [])]

    async def get_item_graph(
        self,
        item_id: int,
        depth: int = 1
    ) -> Dict[str, Any]:
        """Get a graph of relationships starting from an item asynchronously."""
        response = await self._client._request(
            "GET",
            f"{self._base_path}/records/{item_id}/graph",
            params={"depth": depth}
        )

        return response.json()

    def _parse_relationship(self, data: Dict[str, Any]) -> Relationship:
        """Parse API response data into a Relationship model."""
        return Relationship(
            id=data["id"],
            from_item_id=data.get("origin_id"),
            to_item_id=data.get("destination_id"),
            relationship_type=data.get("relationship_type", ""),
            properties=data.get("properties", {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            relationship_pair_id=data.get("relationship_pair_id"),
            data_source_id=data.get("data_source_id"),
        )
