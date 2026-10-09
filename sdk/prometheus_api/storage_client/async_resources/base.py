"""Base resource class for asynchronous API operations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..async_client import AsyncStorageClient


class AsyncBaseResource:
    """Base class for all asynchronous resource handlers.

    Provides common functionality and access to the client instance.
    """

    def __init__(self, client: "AsyncStorageClient"):
        self._client = client

    @property
    def _base_path(self) -> str:
        """Get the base API path including organization and project."""
        return (
            f"/organizations/{self._client.config.organization_id}"
            f"/projects/{self._client.config.project_id}"
        )
