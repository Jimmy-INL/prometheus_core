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

"""Custom exceptions for the storage client library."""

from typing import Any, Optional


class StorageClientError(Exception):
    """Base exception for all storage client errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(StorageClientError):
    """Raised when authentication fails."""

    pass


class ItemNotFoundError(StorageClientError):
    """Raised when a requested item is not found."""

    def __init__(self, item_id: Any, message: Optional[str] = None):
        self.item_id = item_id
        msg = message or f"Item with ID {item_id} not found"
        super().__init__(msg)


class ValidationError(StorageClientError):
    """Raised when input validation fails."""

    pass


class APIError(StorageClientError):
    """Raised when the API returns an error response."""

    def __init__(
        self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None
    ):
        super().__init__(message, details=response_data)
        self.status_code = status_code
        self.response_data = response_data or {}
