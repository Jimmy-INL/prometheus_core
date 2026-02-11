"""Connection configuration for the storage client."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ConnectionConfig(BaseModel):
    """Configuration for connecting to the storage backend.

    This class stores all necessary connection parameters including authentication
    credentials and backend-specific identifiers (hidden from end users).
    """

    # Backend configuration (hidden from users)
    organization_id: int = Field(..., description="Organization identifier")
    project_id: int = Field(..., description="Project identifier")

    # Base URL
    base_url: str = Field(
        default="https://deeplynx.inl.gov/api/v1",
        description="Base URL for the storage backend API"
    )

    # Authentication (either API key pair or JWT token)
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    api_secret: Optional[str] = Field(default=None, description="API secret for authentication")
    jwt_token: Optional[str] = Field(default=None, description="JWT token for authentication")

    # Connection settings
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    verify_ssl: bool = Field(default=True, description="Whether to verify SSL certificates")

    model_config = {
        "frozen": True,  # Make instances immutable
        "extra": "forbid"  # Reject unknown fields
    }

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Ensure base URL doesn't end with a slash."""
        return v.rstrip("/")

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Ensure timeout is positive."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Ensure max_retries is non-negative."""
        if v < 0:
            raise ValueError("max_retries must be non-negative")
        return v

    def model_post_init(self, __context) -> None:
        """Validate that at least one authentication method is provided."""
        if not self.jwt_token and not (self.api_key and self.api_secret):
            raise ValueError(
                "Must provide either jwt_token or both api_key and api_secret"
            )

        if self.jwt_token and (self.api_key or self.api_secret):
            raise ValueError(
                "Cannot provide both jwt_token and api_key/api_secret"
            )

    @property
    def uses_api_key(self) -> bool:
        """Check if configuration uses API key authentication."""
        return bool(self.api_key and self.api_secret)

    @property
    def uses_jwt(self) -> bool:
        """Check if configuration uses JWT authentication."""
        return bool(self.jwt_token)
