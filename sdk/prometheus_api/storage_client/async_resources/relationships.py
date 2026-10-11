# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

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
            "name": relationship.relationship_type,  # API expects 'name' field
            "properties": relationship.properties,
        }

        params: Dict[str, Any] = {"dataSourceId": await self._client._get_data_source_id()}

        response = await self._client._request(
            "POST", f"{self._base_path}/edges", json=payload, params=params
        )

        data = response.json()

        # Some DeepLynx endpoints wrap response in 'value' field
        if isinstance(data, dict) and "value" in data:
            data = data["value"]

        return self._parse_relationship(data)

    async def get(self, relationship_id: int) -> Relationship:
        """Get a relationship by ID asynchronously."""
        response = await self._client._request("GET", f"{self._base_path}/edges/{relationship_id}")

        data = response.json()

        # Some DeepLynx endpoints wrap response in 'value' field
        if isinstance(data, dict) and "value" in data:
            data = data["value"]

        return self._parse_relationship(data)

    async def delete(self, relationship_id: int) -> None:
        """Delete a relationship asynchronously."""
        await self._client._request("DELETE", f"{self._base_path}/edges/{relationship_id}")

    async def bulk_create(self, relationships: List[RelationshipCreate]) -> List[Relationship]:
        """Create multiple relationships in a single request asynchronously."""
        payload = [
            {
                "origin_id": rel.from_item_id,
                "destination_id": rel.to_item_id,
                "name": rel.relationship_type,  # API expects 'name' field
                "properties": rel.properties,
            }
            for rel in relationships
        ]

        params = {"dataSourceId": await self._client._get_data_source_id()}

        response = await self._client._request(
            "POST", f"{self._base_path}/edges/bulk", json=payload, params=params
        )

        data = response.json()

        # API may return edges directly as a list or wrapped in a dict
        if isinstance(data, list):
            edges = data
        else:
            edges = data.get("edges", [])

        return [self._parse_relationship(rel_data) for rel_data in edges]

    async def get_item_relationships(
        self, item_id: int, direction: Optional[str] = None
    ) -> List[Relationship]:
        """Get all relationships for an item asynchronously."""
        # If direction not specified, get both outgoing and incoming
        if direction is None:
            outgoing = await self.get_item_relationships(item_id, "outgoing")
            incoming = await self.get_item_relationships(item_id, "incoming")
            return outgoing + incoming

        params: Dict[str, Any] = {
            "page": 1,
            "pageSize": 100,  # Maximum allowed by DeepLynx API
        }

        # Map direction to isOrigin boolean
        # outgoing: this item is the origin (isOrigin=true)
        # incoming: this item is the destination (isOrigin=false)
        if direction == "outgoing":
            params["isOrigin"] = "true"
        elif direction == "incoming":
            params["isOrigin"] = "false"

        response = await self._client._request(
            "GET", f"{self._base_path}/records/{item_id}/edges", params=params
        )

        data = response.json()

        # API may return edges directly as a list or wrapped in a dict
        if isinstance(data, list):
            edges = data
        else:
            edges = data.get("edges", [])

        # Parse relationships, handling different response formats
        relationships = []
        for rel_data in edges:
            # Check if this is the simplified format (from list endpoint)
            if "relatedRecordId" in rel_data:
                # Simplified format: reconstruct full relationship
                if direction == "outgoing":
                    from_id = item_id
                    to_id = rel_data.get("relatedRecordId")
                else:  # incoming
                    from_id = rel_data.get("relatedRecordId")
                    to_id = item_id

                relationships.append(
                    Relationship(
                        id=rel_data.get("id", 0),
                        from_item_id=from_id,
                        to_item_id=to_id,
                        relationship_type=rel_data.get("name", ""),
                        properties=rel_data.get("properties", {}),
                        created_at=rel_data.get("createdAt"),
                        updated_at=rel_data.get("lastUpdatedAt"),
                        relationship_pair_id=rel_data.get("relationshipId"),
                        data_source_id=rel_data.get("dataSourceId"),
                    )
                )
            else:
                # Full format: use standard parser
                relationships.append(self._parse_relationship(rel_data))

        return relationships

    async def get_item_graph(self, item_id: int, depth: int = 1) -> Dict[str, Any]:
        """Get a graph of relationships starting from an item asynchronously."""
        response = await self._client._request(
            "GET", f"{self._base_path}/records/{item_id}/graph", params={"depth": depth}
        )

        data = response.json()
        return data if isinstance(data, dict) else {"result": data}

    def _parse_relationship(self, data: Dict[str, Any]) -> Relationship:
        """Parse API response data into a Relationship model.

        Note:
            created_at and updated_at are optional as some DeepLynx
            deployments may not return these fields.

        Raises:
            ValueError: If required fields are missing from API response
        """
        # DeepLynx API returns camelCase field names per API docs
        from_item_id = data.get("originId")
        to_item_id = data.get("destinationId")

        # Validate required fields
        if from_item_id is None or to_item_id is None:
            import json
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to parse relationship - missing node IDs. Response data: {json.dumps(data, indent=2)}"
            )
            raise ValueError(
                f"API response missing required node ID fields. "
                f"Response keys: {list(data.keys())}. "
                f"Expected 'originId' and 'destinationId'."
            )

        return Relationship(
            id=data["id"],
            from_item_id=from_item_id,
            to_item_id=to_item_id,
            relationship_type=data.get("name", ""),
            properties=data.get("properties", {}),
            created_at=data.get("createdAt"),
            updated_at=data.get("lastUpdatedAt"),
            relationship_pair_id=data.get("relationshipId"),
            data_source_id=data.get("dataSourceId"),
        )
