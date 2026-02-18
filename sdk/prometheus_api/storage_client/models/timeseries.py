"""Timeseries models for the storage client."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TimeseriesQuery(BaseModel):
    """Represents a timeseries query request."""

    data_source_id: int = Field(..., description="Data source identifier")
    sql_query: str = Field(..., description="SQL query to execute")
    file_type: Optional[str] = Field(default="json", description="Output format (json, csv, etc.)")

    model_config = {
        "from_attributes": True
    }


class TimeseriesResult(BaseModel):
    """Represents the result of a timeseries query."""

    data: Any = Field(..., description="Query result data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Query metadata")

    model_config = {
        "from_attributes": True
    }
