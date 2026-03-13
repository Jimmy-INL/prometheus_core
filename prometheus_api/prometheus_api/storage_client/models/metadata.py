"""Metadata models for the storage client."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class MetadataField(BaseModel):
    """Represents a metadata field with name, value, and optional type."""

    name: str = Field(..., description="Field name")
    value: Any = Field(..., description="Field value")
    type: Optional[str] = Field(None, description="Field type (e.g., 'string', 'number', 'date')")

    model_config = {
        "from_attributes": True
    }
