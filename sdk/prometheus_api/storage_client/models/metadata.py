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

"""Metadata models for the storage client."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class MetadataField(BaseModel):
    """Represents a metadata field with name, value, and optional type."""

    name: str = Field(..., description="Field name")
    value: Any = Field(..., description="Field value")
    type: Optional[str] = Field(None, description="Field type (e.g., 'string', 'number', 'date')")

    model_config = {"from_attributes": True}
