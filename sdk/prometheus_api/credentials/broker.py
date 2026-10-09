"""CredentialBroker interface and core data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, runtime_checkable


class CredentialError(Exception):
    """Raised when a credential cannot be issued (bad request, policy denial, etc.)."""


@dataclass(frozen=True)
class CredentialRequest:
    """Describes the credential a caller needs.

    Attributes:
        user_id: The platform user_id on whose behalf the credential is issued.
        resource: Logical resource identifier.  Registered resources:
            - ``"deeplynx"`` — short-lived JWT for the DeepLynx API.
            - ``"slurm"``    — short-lived token for the SLURM REST API.
            Additional resources are added as new integrations land.
        scope: Optional dict of additional parameters the broker backend may
            use to narrow the credential (e.g. ``{"org_id": "...", "project_id": "..."}``.
    """

    user_id: str
    resource: str
    scope: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Credential:
    """A short-lived, resource-scoped credential returned by the broker.

    Attributes:
        resource: Identifies the target system (mirrors ``CredentialRequest.resource``).
        value: The credential material — structure depends on *resource*:
            - ``"deeplynx"``: ``{"jwt_token": "<token>"}``
            - ``"slurm"``:    ``{"token": "<token>", "user": "<slurm_user>"}``
            Never log or persist this dict.
        expires_at: UTC datetime when the credential expires.  Callers should
            fetch a new credential on the next operation rather than caching.
    """

    resource: str
    value: Dict[str, Any]
    expires_at: datetime


@runtime_checkable
class CredentialBroker(Protocol):
    """Protocol every broker implementation must satisfy.

    Both factors are required on every ``get_credential`` call:
    - **Workload**: transport-level auth (mTLS cert or ``VAULT_AGENT_SECRET``
      header) configured at broker-client construction time — not part of the
      method signature because it is handled by the underlying HTTP client.
    - **User assertion**: ``user_token`` is the raw platform JWT; the broker
      verifies its signature, checks the ``sub`` claim against its per-user
      policy, and refuses if the user has not linked the requested resource.
    """

    async def get_credential(
        self,
        req: CredentialRequest,
        *,
        user_token: str,
    ) -> Credential:
        """Issue a short-lived credential for *req.resource* on behalf of *req.user_id*.

        Args:
            req: Describes the resource and user.
            user_token: The raw platform JWT for the requesting user.

        Returns:
            A ``Credential`` with a populated ``value`` dict and ``expires_at``.

        Raises:
            CredentialError: On authentication failure, policy denial, or
                backend errors.
        """
        ...
