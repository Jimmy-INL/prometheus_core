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

"""Pagination models for the storage client."""

from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageInfo(BaseModel):
    """Information about the current page in a paginated response."""

    page_number: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_count: int = Field(..., description="Total number of items available")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.page_size <= 0:
            return 0
        return (self.total_count + self.page_size - 1) // self.page_size


class Page(BaseModel, Generic[T]):
    """Generic paginated response containing items and page information."""

    items: List[T] = Field(..., description="List of items in the current page")
    page_info: PageInfo = Field(..., description="Pagination information")

    model_config = {"arbitrary_types_allowed": True}
