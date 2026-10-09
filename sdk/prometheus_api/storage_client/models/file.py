"""File models for the storage client."""

from typing import Optional
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class FileMetadata(BaseModel):
    """Metadata for a file stored in the system."""

    id: int = Field(..., description="File ID")
    name: str = Field(..., description="File name")
    description: Optional[str] = Field(None, description="File description")
    file_type: Optional[str] = Field(None, description="MIME type of the file")
    size: Optional[int] = Field(None, description="File size in bytes")
    uri: Optional[str] = Field(None, description="File URI/location")
    created_at: Optional[datetime] = Field(None, description="Upload timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = {"from_attributes": True}


class FileUpload(BaseModel):
    """Model for uploading a new file."""

    file_path: Path = Field(..., description="Path to the file to upload")
    name: Optional[str] = Field(None, description="File name (defaults to filename)")
    description: Optional[str] = Field(None, description="File description")

    @field_validator("file_path")
    @classmethod
    def validate_file_exists(cls, v: Path) -> Path:
        """Ensure the file exists."""
        if not v.exists():
            raise ValueError(f"File does not exist: {v}")
        if not v.is_file():
            raise ValueError(f"Path is not a file: {v}")
        return v

    model_config = {"arbitrary_types_allowed": True}


class ChunkedUploadSession(BaseModel):
    """Represents an active chunked upload session."""

    upload_id: str = Field(..., description="Unique upload session ID")
    file_name: str = Field(..., description="Name of the file being uploaded")
    total_chunks: int = Field(..., description="Total number of chunks")
    chunks_uploaded: int = Field(default=0, description="Number of chunks uploaded so far")

    model_config = {"from_attributes": True}
