"""Item models for the storage client."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Tag(BaseModel):
    """Represents a tag associated with an item."""

    id: Optional[int] = Field(None, description="Tag ID")
    name: str = Field(..., description="Tag name")

    model_config = {"from_attributes": True}


class ItemBase(BaseModel):
    """Base model for item data."""

    name: str = Field(..., description="Item name")
    description: Optional[str] = Field(None, description="Item description")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Custom properties/metadata for the item"
    )
    class_id: Optional[int] = Field(None, description="Class identifier for the item")
    original_id: Optional[str] = Field(None, description="Original identifier from source system")

    model_config = {"from_attributes": True}


class ItemCreate(ItemBase):
    """Model for creating a new item."""

    tags: Optional[List[str]] = Field(
        default=None, description="List of tag names to associate with the item"
    )


class ItemUpdate(BaseModel):
    """Model for updating an existing item. All fields are optional."""

    name: Optional[str] = Field(None, description="Item name")
    description: Optional[str] = Field(None, description="Item description")
    properties: Optional[Dict[str, Any]] = Field(None, description="Custom properties/metadata")
    class_id: Optional[int] = Field(None, description="Class identifier")
    original_id: Optional[str] = Field(None, description="Original identifier")

    model_config = {"from_attributes": True}


class Item(ItemBase):
    """Full item model including system fields."""

    id: int = Field(..., description="Item ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    tags: List[Tag] = Field(default_factory=list, description="Associated tags")

    # System fields (from DeepLynx)
    metatype_id: Optional[int] = Field(None, description="Internal metatype identifier")
    metatype_name: Optional[str] = Field(None, description="Internal metatype name")
    data_source_id: Optional[int] = Field(None, description="Source data identifier")

    model_config = {"from_attributes": True}


class BulkItemCreate(BaseModel):
    """Wrapper for bulk item creation operations."""

    items: List[ItemCreate] = Field(..., description="List of items to create")

    model_config = {"from_attributes": True}
