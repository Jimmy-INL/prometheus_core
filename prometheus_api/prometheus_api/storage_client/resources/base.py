"""Base resource class for synchronous API operations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import StorageClient


class BaseResource:
    """Base class for all synchronous resource handlers.

    Provides common functionality and access to the client instance.
    """

    def __init__(self, client: "StorageClient"):
        self._client = client

    @property
    def _base_path(self) -> str:
        """Get the base API path including organization and project."""
        return (
            f"/organizations/{self._client.config.organization_id}"
            f"/projects/{self._client.config.project_id}"
        )
