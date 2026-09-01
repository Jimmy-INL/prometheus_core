"""Mint short-lived platform JWTs for the authenticated user (identity plane).

The backend mints its own internal JWT after login — never forwards the
session cookie or any external IdP token — so agents can verify *who* is
calling them independent of how the user logged in (local password or a
future OIDC provider).

Verification-side lives in ``prometheus_api.agent.identity``; see
``docs/dev-docs/multi-user-setup.md`` for the full picture (identity plane,
credential plane, per-user worker isolation).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    """Return True when enough env config exists to mint a token."""
    alg = os.environ.get("USER_IDENTITY_ALG", "HS256").upper()
    if alg == "RS256":
        return bool(os.environ.get("USER_IDENTITY_PRIVATE_KEY"))
    return bool(os.environ.get("USER_IDENTITY_SECRET"))


def mint_for_user(user_id: str) -> Optional[str]:
    """Mint a short-lived platform JWT for *user_id*, or ``None`` if unavailable.

    Returns ``None`` (rather than raising) both when identity isn't configured
    and when minting fails for any reason — mirrors ``USER_IDENTITY_REQUIRED=false``
    dev/CI mode on the agent side: the backend simply omits ``userToken`` and
    agents fall back to a synthetic ``"local"`` identity.
    """
    if not user_id or not _is_configured():
        return None
    try:
        from prometheus_api.agent.identity import mint_user_token

        ttl = int(os.environ.get("USER_IDENTITY_TTL", "7200"))
        return mint_user_token(user_id, ttl_seconds=ttl)
    except Exception as exc:
        logger.warning("Failed to mint user token for %r: %s", user_id, exc)
        return None
