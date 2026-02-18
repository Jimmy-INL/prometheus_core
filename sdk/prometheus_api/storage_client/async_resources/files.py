"""Async files resource."""

from pathlib import Path
from typing import Optional
from ..models.file import FileMetadata
from .base import AsyncBaseResource


class AsyncFilesResource(AsyncBaseResource):
    """Handles async operations related to file storage and retrieval."""

    async def upload(
        self,
        file_path: Path,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> FileMetadata:
        """Upload a file to storage asynchronously."""
        if not file_path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        file_name = name or file_path.name

        with open(file_path, "rb") as f:
            files = {"file": (file_name, f)}
            data = {}

            if description:
                data["description"] = description

            response = await self._client._request(
                "POST",
                f"{self._base_path}/files",
                files=files,
                data=data
            )

        return self._parse_file_metadata(response.json())

    async def upload_chunked(
        self,
        file_path: Path,
        chunk_size: int = 5 * 1024 * 1024,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> FileMetadata:
        """Upload a large file in chunks asynchronously."""
        from ..utils.streaming import AsyncChunkedUploader

        uploader = AsyncChunkedUploader(self._client, chunk_size)
        return await uploader.upload(file_path, name, description)

    async def get(self, file_id: int) -> FileMetadata:
        """Get file metadata by ID asynchronously."""
        response = await self._client._request(
            "GET",
            f"{self._base_path}/files/{file_id}"
        )

        return self._parse_file_metadata(response.json())

    async def download(self, file_id: int, output_path: Path) -> None:
        """Download a file to local storage asynchronously."""
        response = await self._client._request(
            "GET",
            f"{self._base_path}/files/{file_id}/download"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

    async def delete(self, file_id: int) -> None:
        """Delete a file asynchronously."""
        await self._client._request(
            "DELETE",
            f"{self._base_path}/files/{file_id}"
        )

    def _parse_file_metadata(self, data: dict) -> FileMetadata:
        """Parse API response data into FileMetadata model."""
        return FileMetadata(
            id=data["id"],
            name=data.get("file_name", ""),
            description=data.get("description"),
            file_type=data.get("file_type"),
            size=data.get("file_size"),
            uri=data.get("adapter_file_path"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
