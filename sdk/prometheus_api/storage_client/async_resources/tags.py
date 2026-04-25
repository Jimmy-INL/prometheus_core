"""Async tags resource."""

from typing import List
from ..models.tag import TagModel
from .base import AsyncBaseResource


class AsyncTagsResource(AsyncBaseResource):
    """Handles async operations for project-level tags."""

    @property
    def _project_path(self) -> str:
        return f"/projects/{self._client.config.project_id}/tags"

    async def list(self) -> List[TagModel]:
        """List all tags in the active project."""
        response = await self._client._request("GET", self._project_path)
        data = response.json()
        records = data if isinstance(data, list) else data.get("value", data.get("tags", []))
        return [TagModel(**t) for t in records]

    async def create(self, name: str) -> TagModel:
        """Create a new tag in the active project."""
        normalized = str(name or "").strip()
        if not normalized:
            raise ValueError("Tag name must be non-empty")

        response = await self._client._request(
            "POST", self._project_path, json={"name": normalized}
        )
        data = response.json()
        record = data if (isinstance(data, dict) and data.get("id")) else data.get("value", data)
        return TagModel(**record)

    async def get_or_create(self, name: str) -> TagModel:
        """Return the tag with the given name, creating it if it doesn't exist."""
        normalized = str(name or "").strip()
        if not normalized:
            raise ValueError("Tag name must be non-empty")

        for tag in await self.list():
            if tag.name == normalized:
                return tag
        return await self.create(normalized)

    async def resolve_ids(self, names: List[str]) -> List[int]:
        """Resolve a list of project tag names to positive integer IDs."""
        ids = []
        seen = set()
        for raw_name in names:
            name = str(raw_name or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            tag = await self.get_or_create(name)
            if tag.id is None or int(tag.id) <= 0:
                raise ValueError(
                    f"DeepLynx project tag '{name}' did not return a valid positive id: "
                    f"{tag.model_dump()}"
                )
            ids.append(int(tag.id))
        return ids
