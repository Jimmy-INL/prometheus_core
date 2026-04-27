"""Storage Client Library - A generic abstraction for storage backend operations."""

from .client import StorageClient
from .async_client import AsyncStorageClient
from .connection import ConnectionConfig
from .models.item import Item, ItemCreate, ItemUpdate, Tag
from .models.file import FileMetadata, FileUpload
from .models.relationship import Relationship, RelationshipCreate
from .models.pagination import Page, PageInfo
from .exceptions import (
    StorageClientError,
    AuthenticationError,
    ItemNotFoundError,
    ValidationError,
    APIError,
)

from prometheus_api import __version__

__all__ = [
    # Clients
    "StorageClient",
    "AsyncStorageClient",
    "__version__",
    # Configuration
    "ConnectionConfig",
    # Models
    "Item",
    "ItemCreate",
    "ItemUpdate",
    "Tag",
    "FileMetadata",
    "FileUpload",
    "Relationship",
    "RelationshipCreate",
    "Page",
    "PageInfo",
    # Exceptions
    "StorageClientError",
    "AuthenticationError",
    "ItemNotFoundError",
    "ValidationError",
    "APIError",
]
