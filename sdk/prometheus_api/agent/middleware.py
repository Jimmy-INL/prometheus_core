"""
Starlette middleware for Bearer token authentication in A2A agents.

This module provides reusable authentication middleware for Agent-to-Agent
communication using shared secrets.
"""

import os
import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """
    Middleware to verify Bearer token authentication for A2A requests.

    Validates that all incoming requests contain a valid Bearer token
    in the Authorization header matching a configured secret.

    Args:
        app: The Starlette application
        secret: The shared secret for authentication (optional, reads from AGENT_SECRET env var)
        required: Whether authentication is required (default: True)

    Example:
        >>> from starlette.applications import Starlette
        >>> from agent.middleware import BearerTokenMiddleware
        >>>
        >>> app = Starlette()
        >>> app.add_middleware(BearerTokenMiddleware, secret="my-secret", required=True)

    Environment Variables:
        AGENT_SECRET: The shared secret for authentication
        AGENT_SECRET_REQUIRED: Whether to enforce authentication (default: true)

    Security Notes:
        - Health check (/health) and agent card (/.well-known/agent.json) endpoints are exempt
        - Token values are never logged (only validation status)
        - Returns 401 Unauthorized with JSON-RPC 2.0 error format on failure
    """

    def __init__(self, app, secret: Optional[str] = None, required: bool = True):
        """
        Initialize the Bearer token middleware.

        Args:
            app: The Starlette application
            secret: Shared secret for authentication (defaults to AGENT_SECRET env var)
            required: Whether authentication is required (default: True)

        Raises:
            ValueError: If required=True but no secret is provided or configured
        """
        super().__init__(app)
        self.secret = secret or os.getenv("AGENT_SECRET")
        self.required = required

        if self.required and not self.secret:
            logger.error("AGENT_SECRET is required but not configured")
            raise ValueError("AGENT_SECRET environment variable must be set")

        if not self.secret:
            logger.warning("AGENT_SECRET not set - authentication is disabled")

    async def dispatch(self, request, call_next):
        """
        Process each request and validate Bearer token.

        Args:
            request: The incoming Starlette request
            call_next: The next middleware/handler in the chain

        Returns:
            Response from downstream handlers or 401 Unauthorized
        """
        # Skip authentication if not required
        if not self.required or not self.secret:
            return await call_next(request)

        # Skip authentication for health check and public metadata endpoints.
        if request.url.path in [
            "/health",
            "/.well-known/agent.json",
            "/.well-known/agent-card.json",
            "/api/agent-card",
        ]:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("authorization", "")

        # Validate header exists and format is correct
        if not auth_header:
            logger.warning(f"Request to {request.url.path} missing Authorization header")
            return self._unauthorized_response("Missing Authorization header")

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"Request to {request.url.path} has invalid Authorization format")
            return self._unauthorized_response(
                "Invalid Authorization format (expected: Bearer <token>)"
            )

        token = parts[1]

        # Verify token matches secret
        if token != self.secret:
            logger.warning(f"Request to {request.url.path} has invalid token")
            return self._unauthorized_response("Invalid token")

        # Token is valid - attach to request state for potential downstream use
        request.state.authenticated = True
        request.state.token = token

        # Proceed with request
        return await call_next(request)

    def _unauthorized_response(self, message: str) -> JSONResponse:
        """
        Return 401 Unauthorized with JSON-RPC 2.0 error format.

        Args:
            message: Error message describing the authentication failure

        Returns:
            JSONResponse with 401 status code and JSON-RPC error
        """
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32600,
                    "message": "Invalid Request - Authentication Failed",
                    "data": {"reason": message},
                },
                "id": None,
            },
        )
