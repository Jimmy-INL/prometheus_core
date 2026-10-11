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

"""Tag models for the storage client."""

from typing import Optional
from pydantic import BaseModel, Field


class TagModel(BaseModel):
    """Represents a tag that can be attached to items."""

    id: Optional[int] = Field(None, description="Tag ID")
    name: str = Field(..., description="Tag name")

    model_config = {"from_attributes": True}
