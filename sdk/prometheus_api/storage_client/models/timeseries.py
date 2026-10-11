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

"""Timeseries models for the storage client."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TimeseriesQuery(BaseModel):
    """Represents a timeseries query request."""

    data_source_id: int = Field(..., description="Data source identifier")
    sql_query: str = Field(..., description="SQL query to execute")
    file_type: Optional[str] = Field(default="json", description="Output format (json, csv, etc.)")

    model_config = {"from_attributes": True}


class TimeseriesResult(BaseModel):
    """Represents the result of a timeseries query."""

    data: Any = Field(..., description="Query result data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Query metadata")

    model_config = {"from_attributes": True}
