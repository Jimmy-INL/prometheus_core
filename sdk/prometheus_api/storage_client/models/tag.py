"""Tag models for the storage client."""

from typing import Optional
from pydantic import BaseModel, Field


class TagModel(BaseModel):
    """Represents a tag that can be attached to items."""

    id: Optional[int] = Field(None, description="Tag ID")
    name: str = Field(..., description="Tag name")

    model_config = {"from_attributes": True}
