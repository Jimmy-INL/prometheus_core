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

        Returns Authorization header with Bearer token.
        For API key auth, gets a JWT token first.
        """
        # For API key auth, get JWT token first
        if self.config.uses_api_key:
            if not self._jwt_token or (self._managed_token and self._needs_refresh()):
                self._refresh_token()

        return {"Authorization": f"Bearer {self._jwt_token}"}

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
            # DeepLynx uses /oauth/tokens endpoint with JSON body
            response = self.client.post(
                f"{self.config.base_url}/oauth/tokens",
                json={
                    "apiKey": self.config.api_key,
                    "apiSecret": self.config.api_secret,
                    "expirationMinutes": None,  # Use default expiration
                },
                headers={"Content-Type": "application/json"},
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            # DeepLynx returns the JWT token directly as plain text
            self._jwt_token = response.text.strip()

            if not self._jwt_token:
                raise AuthenticationError("No token in response")

            # Default expiration is 1 hour (60 minutes)
            expires_in = 3600  # 1 hour in seconds
            self._token_expiry = time.time() + expires_in

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API credentials")
            elif e.response.status_code == 404:
                raise AuthenticationError("OAuth endpoint not found - check base URL")
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

        Returns Authorization header with Bearer token.
        For API key auth, gets a JWT token first.
        """
        # For API key auth, get JWT token first
        if self.config.uses_api_key:
            if not self._jwt_token or (self._managed_token and self._needs_refresh()):
                await self._refresh_token()

        return {"Authorization": f"Bearer {self._jwt_token}"}

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
            # DeepLynx uses /oauth/tokens endpoint with JSON body
            response = await self.client.post(
                f"{self.config.base_url}/oauth/tokens",
                json={
                    "apiKey": self.config.api_key,
                    "apiSecret": self.config.api_secret,
                    "expirationMinutes": None,  # Use default expiration
                },
                headers={"Content-Type": "application/json"},
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            # DeepLynx returns the JWT token directly as plain text
            self._jwt_token = response.text.strip()

            if not self._jwt_token:
                raise AuthenticationError("No token in response")

            # Default expiration is 1 hour (60 minutes)
            expires_in = 3600  # 1 hour in seconds
            self._token_expiry = time.time() + expires_in

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API credentials")
            elif e.response.status_code == 404:
                raise AuthenticationError("OAuth endpoint not found - check base URL")
            raise AuthenticationError(f"Token refresh failed: {e}")
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {e}")
