"""Files resource for synchronous operations."""

from pathlib import Path
from typing import Optional
from ..models.file import FileMetadata
from .base import BaseResource


class FilesResource(BaseResource):
    """Handles operations related to file storage and retrieval."""

    def upload(
        self,
        file_path: Path,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> FileMetadata:
        """Upload a file to storage.

        Args:
            file_path: Path to the file to upload
            name: Optional custom name (defaults to filename)
            description: Optional file description

        Returns:
            File metadata

        Example:
            ```python
            file_meta = client.files.upload(
                Path("data.csv"),
                description="Experiment results"
            )
            ```
        """
        if not file_path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        file_name = name or file_path.name

        # Open and upload file
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f)}
            data = {}

            if description:
                data["description"] = description

            response = self._client._request(
                "POST",
                f"{self._base_path}/files",
                files=files,
                data=data
            )

        return self._parse_file_metadata(response.json())

    def upload_chunked(
        self,
        file_path: Path,
        chunk_size: int = 5 * 1024 * 1024,  # 5MB default
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> FileMetadata:
        """Upload a large file in chunks.

        Args:
            file_path: Path to the file to upload
            chunk_size: Size of each chunk in bytes
            name: Optional custom name
            description: Optional file description

        Returns:
            File metadata

        Example:
            ```python
            # Upload large file in 10MB chunks
            file_meta = client.files.upload_chunked(
                Path("large_data.zip"),
                chunk_size=10 * 1024 * 1024
            )
            ```
        """
        from ..utils.streaming import ChunkedUploader

        uploader = ChunkedUploader(self._client, chunk_size)
        return uploader.upload(file_path, name, description)

    def get(self, file_id: int) -> FileMetadata:
        """Get file metadata by ID.

        Args:
            file_id: File identifier

        Returns:
            File metadata

        Raises:
            ItemNotFoundError: If file doesn't exist
        """
        response = self._client._request(
            "GET",
            f"{self._base_path}/files/{file_id}"
        )

        return self._parse_file_metadata(response.json())

    def download(self, file_id: int, output_path: Path) -> None:
        """Download a file to local storage.

        Args:
            file_id: File identifier
            output_path: Where to save the downloaded file

        Raises:
            ItemNotFoundError: If file doesn't exist

        Example:
            ```python
            client.files.download(123, Path("downloaded.csv"))
            ```
        """
        response = self._client._request(
            "GET",
            f"{self._base_path}/files/{file_id}/download"
        )

        # Write file content
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

    def delete(self, file_id: int) -> None:
        """Delete a file.

        Args:
            file_id: File identifier

        Raises:
            ItemNotFoundError: If file doesn't exist
        """
        self._client._request(
            "DELETE",
            f"{self._base_path}/files/{file_id}"
        )

    def _parse_file_metadata(self, data: dict) -> FileMetadata:
        """Parse API response data into FileMetadata model.

        Args:
            data: Raw API response data

        Returns:
            Parsed FileMetadata object
        """
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
