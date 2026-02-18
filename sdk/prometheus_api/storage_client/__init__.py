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

__version__ = "0.1.0"

__all__ = [
    # Clients
    "StorageClient",
    "AsyncStorageClient",
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
