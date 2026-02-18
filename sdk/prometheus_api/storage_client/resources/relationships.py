"""Relationships resource for synchronous operations."""

from typing import Any, Dict, List, Optional
from ..models.relationship import Relationship, RelationshipCreate
from .base import BaseResource


class RelationshipsResource(BaseResource):
    """Handles operations related to relationships between items."""

    def create(self, relationship: RelationshipCreate) -> Relationship:
        """Create a new relationship between two items.

        Args:
            relationship: Relationship creation data

        Returns:
            Created relationship with ID and timestamps

        Example:
            ```python
            rel = client.relationships.create(RelationshipCreate(
                from_item_id=1,
                to_item_id=2,
                relationship_type="depends_on",
                properties={"strength": "strong"}
            ))
            ```
        """
        payload = {
            "origin_id": relationship.from_item_id,
            "destination_id": relationship.to_item_id,
            "relationship_type": relationship.relationship_type,
            "properties": relationship.properties,
        }

        params = {
            "dataSourceId": self._client._get_data_source_id()
        }

        response = self._client._request(
            "POST",
            f"{self._base_path}/edges",
            json=payload,
            params=params
        )

        return self._parse_relationship(response.json())

    def get(self, relationship_id: int) -> Relationship:
        """Get a relationship by ID.

        Args:
            relationship_id: Relationship identifier

        Returns:
            Relationship data

        Raises:
            ItemNotFoundError: If relationship doesn't exist
        """
        response = self._client._request(
            "GET",
            f"{self._base_path}/edges/{relationship_id}"
        )

        return self._parse_relationship(response.json())

    def delete(self, relationship_id: int) -> None:
        """Delete a relationship.

        Args:
            relationship_id: Relationship identifier

        Raises:
            ItemNotFoundError: If relationship doesn't exist
        """
        self._client._request(
            "DELETE",
            f"{self._base_path}/edges/{relationship_id}"
        )

    def bulk_create(self, relationships: List[RelationshipCreate]) -> List[Relationship]:
        """Create multiple relationships in a single request.

        Args:
            relationships: List of relationships to create

        Returns:
            List of created relationships

        Example:
            ```python
            rels = client.relationships.bulk_create([
                RelationshipCreate(from_item_id=1, to_item_id=2, relationship_type="links"),
                RelationshipCreate(from_item_id=2, to_item_id=3, relationship_type="links")
            ])
            ```
        """
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
            "dataSourceId": self._client._get_data_source_id()
        }

        response = self._client._request(
            "POST",
            f"{self._base_path}/edges/bulk",
            json=payload,
            params=params
        )

        data = response.json()
        return [self._parse_relationship(rel_data) for rel_data in data.get("edges", [])]

    def get_item_relationships(
        self,
        item_id: int,
        direction: Optional[str] = None
    ) -> List[Relationship]:
        """Get all relationships for an item.

        Args:
            item_id: Item identifier
            direction: Filter by direction ('outgoing', 'incoming', or None for both)

        Returns:
            List of relationships

        Example:
            ```python
            # Get all relationships
            all_rels = client.relationships.get_item_relationships(123)

            # Get only outgoing relationships
            outgoing = client.relationships.get_item_relationships(123, "outgoing")
            ```
        """
        params = {}
        if direction:
            params["direction"] = direction

        response = self._client._request(
            "GET",
            f"{self._base_path}/records/{item_id}/edges",
            params=params
        )

        data = response.json()
        return [self._parse_relationship(rel_data) for rel_data in data.get("edges", [])]

    def get_item_graph(
        self,
        item_id: int,
        depth: int = 1
    ) -> Dict[str, Any]:
        """Get a graph of relationships starting from an item.

        Args:
            item_id: Starting item identifier
            depth: How many levels deep to traverse

        Returns:
            Graph structure with items and relationships

        Example:
            ```python
            graph = client.relationships.get_item_graph(123, depth=2)
            ```
        """
        response = self._client._request(
            "GET",
            f"{self._base_path}/records/{item_id}/graph",
            params={"depth": depth}
        )

        return response.json()

    def _parse_relationship(self, data: Dict[str, Any]) -> Relationship:
        """Parse API response data into a Relationship model.

        Args:
            data: Raw API response data

        Returns:
            Parsed Relationship object
        """
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
