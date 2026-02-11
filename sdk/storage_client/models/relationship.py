"""Relationship models for the storage client."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class RelationshipBase(BaseModel):
    """Base model for relationship data."""

    from_item_id: int = Field(..., description="Source item ID")
    to_item_id: int = Field(..., description="Target item ID")
    relationship_type: str = Field(..., description="Type of relationship")
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom properties for the relationship"
    )

    model_config = {
        "from_attributes": True
    }


class RelationshipCreate(RelationshipBase):
    """Model for creating a new relationship."""
    pass


class Relationship(RelationshipBase):
    """Full relationship model including system fields."""

    id: int = Field(..., description="Relationship ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # System fields (from DeepLynx)
    relationship_pair_id: Optional[int] = Field(None, description="Internal relationship pair ID")
    data_source_id: Optional[int] = Field(None, description="Source data identifier")

    model_config = {
        "from_attributes": True
    }


class BulkRelationshipCreate(BaseModel):
    """Wrapper for bulk relationship creation operations."""

    relationships: List[RelationshipCreate] = Field(..., description="List of relationships to create")

    model_config = {
        "from_attributes": True
    }
