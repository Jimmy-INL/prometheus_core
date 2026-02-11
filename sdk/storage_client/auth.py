"""Authentication handlers for the storage client."""

import time
from typing import Dict, Optional
import httpx
from .connection import ConnectionConfig
from .exceptions import AuthenticationError


class AuthHandler:
    """Synchronous authentication handler with automatic token refresh."""

    def __init__(self, config: ConnectionConfig, client: httpx.Client):
        self.config = config
        self.client = client
        self._jwt_token: Optional[str] = config.jwt_token
        self._token_expiry: Optional[float] = None

        # If JWT token is provided, we don't manage expiry
        if config.jwt_token:
            self._managed_token = False
        else:
            self._managed_token = True

    def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests.

        Returns appropriate headers based on authentication method.
        For API key auth, returns x-api-key and x-api-secret headers.
        For JWT auth, returns Authorization header with Bearer token.
        """
        if self.config.uses_api_key:
            return {
                "x-api-key": self.config.api_key,
                "x-api-secret": self.config.api_secret,
            }
        else:
            # Check if token needs refresh
            if self._managed_token and self._needs_refresh():
                self._refresh_token()

            return {
                "Authorization": f"Bearer {self._jwt_token}"
            }

    def _needs_refresh(self) -> bool:
        """Check if the JWT token needs to be refreshed."""
        if not self._token_expiry:
            return False

        # Refresh if token expires in less than 5 minutes
        return time.time() >= (self._token_expiry - 300)

    def _refresh_token(self) -> None:
        """Refresh the JWT token using API credentials."""
        if not self.config.uses_api_key:
            raise AuthenticationError("Cannot refresh token without API credentials")

        try:
            response = self.client.post(
                f"{self.config.base_url}/auth/token",
                headers={
                    "x-api-key": self.config.api_key,
                    "x-api-secret": self.config.api_secret,
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            data = response.json()
            self._jwt_token = data.get("token")

            # Set expiry (typically tokens are valid for 24 hours)
            expires_in = data.get("expires_in", 86400)  # Default 24 hours
            self._token_expiry = time.time() + expires_in

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API credentials")
            raise AuthenticationError(f"Token refresh failed: {e}")
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {e}")


class AsyncAuthHandler:
    """Asynchronous authentication handler with automatic token refresh."""

    def __init__(self, config: ConnectionConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client
        self._jwt_token: Optional[str] = config.jwt_token
        self._token_expiry: Optional[float] = None

        # If JWT token is provided, we don't manage expiry
        if config.jwt_token:
            self._managed_token = False
        else:
            self._managed_token = True

    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests.

        Returns appropriate headers based on authentication method.
        For API key auth, returns x-api-key and x-api-secret headers.
        For JWT auth, returns Authorization header with Bearer token.
        """
        if self.config.uses_api_key:
            return {
                "x-api-key": self.config.api_key,
                "x-api-secret": self.config.api_secret,
            }
        else:
            # Check if token needs refresh
            if self._managed_token and self._needs_refresh():
                await self._refresh_token()

            return {
                "Authorization": f"Bearer {self._jwt_token}"
            }

    def _needs_refresh(self) -> bool:
        """Check if the JWT token needs to be refreshed."""
        if not self._token_expiry:
            return False

        # Refresh if token expires in less than 5 minutes
        return time.time() >= (self._token_expiry - 300)

    async def _refresh_token(self) -> None:
        """Refresh the JWT token using API credentials."""
        if not self.config.uses_api_key:
            raise AuthenticationError("Cannot refresh token without API credentials")

        try:
            response = await self.client.post(
                f"{self.config.base_url}/auth/token",
                headers={
                    "x-api-key": self.config.api_key,
                    "x-api-secret": self.config.api_secret,
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            data = response.json()
            self._jwt_token = data.get("token")

            # Set expiry (typically tokens are valid for 24 hours)
            expires_in = data.get("expires_in", 86400)  # Default 24 hours
            self._token_expiry = time.time() + expires_in

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API credentials")
            raise AuthenticationError(f"Token refresh failed: {e}")
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {e}")
