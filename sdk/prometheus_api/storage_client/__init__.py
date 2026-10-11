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
