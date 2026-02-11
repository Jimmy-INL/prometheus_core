"""Connection configuration for the storage client."""

import os
from pathlib import Path
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

    @classmethod
    def from_env(
        cls,
        env_file: Optional[Path] = None,
        organization_id: Optional[int] = None,
        project_id: Optional[int] = None,
        **kwargs
    ) -> "ConnectionConfig":
        """Create configuration from environment variables.

        Loads credentials from environment variables or a .env file.

        Expected environment variables:
        - DEEPLYNX_KEY: API key for authentication
        - DEEPLYNX_SECRET: API secret for authentication
        - DEEPLYNX_ORG_ID: Organization ID (optional if passed as parameter)
        - DEEPLYNX_PROJECT_ID: Project ID (optional if passed as parameter)
        - DEEPLYNX_BASE_URL: Base URL (optional)
        - DEEPLYNX_JWT_TOKEN: JWT token (alternative to API key/secret)

        Args:
            env_file: Optional path to .env file (default: searches for .env in current dir)
            organization_id: Organization ID (overrides env var)
            project_id: Project ID (overrides env var)
            **kwargs: Additional ConnectionConfig parameters

        Returns:
            ConnectionConfig instance

        Raises:
            ValueError: If required credentials are missing

        Example:
            ```python
            # Load from .env file in current directory
            config = ConnectionConfig.from_env()

            # Load from specific .env file
            config = ConnectionConfig.from_env(env_file=Path("/path/to/.env"))

            # Override with parameters
            config = ConnectionConfig.from_env(
                organization_id=123,
                project_id=456
            )
            ```
        """
        # Load .env file if it exists
        if env_file and env_file.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
            except ImportError:
                raise ImportError(
                    "python-dotenv is required for .env file support. "
                    "Install it with: pip install python-dotenv"
                )
        elif env_file is None:
            # Try to load from default .env location
            default_env = Path.cwd() / ".env"
            if default_env.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(default_env)
                except ImportError:
                    pass  # Silently skip if dotenv not installed

        # Get values from environment with fallback to kwargs
        api_key = os.getenv("DEEPLYNX_KEY") or kwargs.pop("api_key", None)
        api_secret = os.getenv("DEEPLYNX_SECRET") or kwargs.pop("api_secret", None)
        jwt_token = os.getenv("DEEPLYNX_JWT_TOKEN") or kwargs.pop("jwt_token", None)

        # Organization and project IDs
        org_id = organization_id or os.getenv("DEEPLYNX_ORG_ID")
        proj_id = project_id or os.getenv("DEEPLYNX_PROJECT_ID")

        if org_id is not None:
            org_id = int(org_id)
        if proj_id is not None:
            proj_id = int(proj_id)

        # Base URL (optional)
        base_url = os.getenv("DEEPLYNX_BASE_URL") or kwargs.pop("base_url", "https://deeplynx.inl.gov/api/v1")

        # Validate required fields
        if org_id is None:
            raise ValueError(
                "organization_id must be provided either as parameter or "
                "in DEEPLYNX_ORG_ID environment variable"
            )
        if proj_id is None:
            raise ValueError(
                "project_id must be provided either as parameter or "
                "in DEEPLYNX_PROJECT_ID environment variable"
            )

        # Create config
        return cls(
            organization_id=org_id,
            project_id=proj_id,
            api_key=api_key,
            api_secret=api_secret,
            jwt_token=jwt_token,
            base_url=base_url,
            **kwargs
        )
