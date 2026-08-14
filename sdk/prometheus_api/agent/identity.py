"""Per-request user identity: minting, verification, and request-scoped propagation.

The platform mints its own short-lived internal JWT after a user logs in, independent
of how authentication happened (Okta, generic OIDC, local password).  This token is what
propagates to agents — never the external IdP token — so the trust model works even when
the deployment has no federated IdP.

Usage
-----
Frontend (mint on each turn)::

    from prometheus_api.agent.identity import mint_user_token
    token = mint_user_token(user_id="alice")

Base class (verify and scope)::

    from prometheus_api.agent.identity import (
        identity_scope, verify_user_token, get_current_identity, current_user_id,
        USER_TOKEN_METADATA_KEY,
    )
    identity = verify_user_token(raw_token)
    with identity_scope(identity):
        params["user_id"] = current_user_id()
        await agent._execute(params, context, event_queue)

Downstream agent helpers::

    from prometheus_api.agent.identity import get_current_identity, USER_TOKEN_METADATA_KEY
    raw = get_current_identity().raw_token
    message_metadata = {USER_TOKEN_METADATA_KEY: raw}   # merge into outbound A2A
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

import jwt

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


#: Key used to carry the user token inside A2A message.metadata.
#: The base class reads this key; outbound propagation should use the same key.
USER_TOKEN_METADATA_KEY = "userToken"

# Defaults — can all be overridden via env vars.
_DEFAULT_ISS = "prometheus-platform"
_DEFAULT_AUD = "prometheus-agents"
_DEFAULT_ALG_HS = "HS256"
_DEFAULT_ALG_RS = "RS256"
_DEFAULT_TTL = 7200  # generous default; background turns can be long


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserIdentity:
    """Verified identity extracted from a platform-minted JWT.

    All fields come from *verified* claims — never from raw, unvalidated input.
    """

    user_id: str
    """The canonical user identifier (JWT ``sub`` claim)."""

    claims: dict[str, Any]
    """All decoded claims from the verified token (read-only copy)."""

    raw_token: str
    """The original token string, for forwarding to downstream A2A hops."""


class IdentityError(Exception):
    """Raised when a token cannot be verified or is missing required claims."""


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------

def mint_user_token(
    user_id: str,
    *,
    extra_claims: Optional[dict[str, Any]] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    """Mint a short-lived platform JWT for *user_id*.

    Algorithm and key are selected from environment variables:
    - ``USER_IDENTITY_ALG=RS256`` + ``USER_IDENTITY_PRIVATE_KEY`` — asymmetric;
      the private key is the PEM string (with or without passphrase).
    - ``USER_IDENTITY_ALG=HS256`` (default) + ``USER_IDENTITY_SECRET`` — HMAC.

    Args:
        user_id: The canonical identifier for the authenticated user.
        extra_claims: Additional claims to embed (will not override ``sub``/``iat``/``exp``/``iss``/``aud``).
        ttl_seconds: Token lifetime; defaults to ``USER_IDENTITY_TTL`` env var
            (seconds, default 7200).

    Returns:
        A signed JWT string.
    """
    alg = _env("USER_IDENTITY_ALG", _DEFAULT_ALG_HS).upper()
    iss = _env("USER_IDENTITY_ISS", _DEFAULT_ISS)
    aud = _env("USER_IDENTITY_AUD", _DEFAULT_AUD)
    ttl = ttl_seconds if ttl_seconds is not None else _int_env("USER_IDENTITY_TTL", _DEFAULT_TTL)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": iss,
        "aud": aud,
    }
    if extra_claims:
        for k, v in extra_claims.items():
            if k not in ("sub", "iat", "exp", "iss", "aud"):
                payload[k] = v

    key = _get_signing_key(alg)
    return jwt.encode(payload, key, algorithm=alg)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_user_token(token: str) -> UserIdentity:
    """Verify a platform JWT and return the extracted identity.

    Checks signature, expiry, issuer, and audience.  All checks are
    performed against the *current* environment configuration — if the
    secret/key or ISS/AUD have changed since the token was minted the
    token will be rejected.

    Raises:
        IdentityError: If the token is invalid, expired, or has wrong iss/aud.
    """
    if not token or not isinstance(token, str):
        raise IdentityError("userToken is missing or not a string")

    alg = _env("USER_IDENTITY_ALG", _DEFAULT_ALG_HS).upper()
    iss = _env("USER_IDENTITY_ISS", _DEFAULT_ISS)
    aud = _env("USER_IDENTITY_AUD", _DEFAULT_AUD)

    key = _get_verification_key(alg)

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[alg],
            issuer=iss,
            audience=aud,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise IdentityError("userToken has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise IdentityError("userToken audience mismatch") from exc
    except jwt.InvalidIssuerError as exc:
        raise IdentityError("userToken issuer mismatch") from exc
    except jwt.InvalidSignatureError as exc:
        raise IdentityError("userToken signature verification failed") from exc
    except jwt.DecodeError as exc:
        raise IdentityError(f"userToken could not be decoded: {exc}") from exc
    except jwt.PyJWTError as exc:
        raise IdentityError(f"userToken invalid: {exc}") from exc

    user_id = claims.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise IdentityError("userToken missing or invalid 'sub' claim")

    return UserIdentity(user_id=user_id, claims=dict(claims), raw_token=token)


# ---------------------------------------------------------------------------
# Request-scoped identity (ContextVar — safe across concurrent async requests)
# ---------------------------------------------------------------------------

_current_identity: ContextVar[Optional[UserIdentity]] = ContextVar(
    "current_identity", default=None
)


@contextmanager
def identity_scope(identity: Optional[UserIdentity]) -> Iterator[None]:
    """Bind *identity* as the current user for the duration of this context.

    Mirrors the ``llm_request_context`` pattern in the client-agent's
    ``orchestrator/runtime.py``.  Uses a ``ContextVar`` so concurrent
    async tasks never share identity state.

    Example::

        identity = verify_user_token(raw_token)
        with identity_scope(identity):
            result = await agent._execute(params, context, event_queue)
    """
    token = _current_identity.set(identity)
    try:
        yield
    finally:
        _current_identity.reset(token)


def get_current_identity() -> Optional[UserIdentity]:
    """Return the verified identity for the current async task, or ``None``.

    Returns ``None`` when called outside an :func:`identity_scope` context
    (e.g. during startup or in background tasks that carry no user identity).
    """
    return _current_identity.get()


def current_user_id() -> Optional[str]:
    """Convenience accessor; returns ``identity.user_id`` or ``None``."""
    identity = _current_identity.get()
    return identity.user_id if identity is not None else None


# ---------------------------------------------------------------------------
# Internal key helpers
# ---------------------------------------------------------------------------

def _get_signing_key(alg: str) -> Any:
    """Return the signing key for *alg*.  Raises ``IdentityError`` if unconfigured."""
    if alg == _DEFAULT_ALG_HS:
        secret = _env("USER_IDENTITY_SECRET")
        if not secret:
            raise IdentityError(
                "USER_IDENTITY_SECRET is required for HS256 identity tokens"
            )
        return secret
    if alg == _DEFAULT_ALG_RS:
        key_pem = _env("USER_IDENTITY_PRIVATE_KEY")
        if not key_pem:
            raise IdentityError(
                "USER_IDENTITY_PRIVATE_KEY (PEM) is required for RS256 identity tokens"
            )
        return key_pem
    raise IdentityError(f"Unsupported USER_IDENTITY_ALG: {alg!r}")


def _get_verification_key(alg: str) -> Any:
    """Return the verification key for *alg*.  Raises ``IdentityError`` if unconfigured."""
    if alg == _DEFAULT_ALG_HS:
        secret = _env("USER_IDENTITY_SECRET")
        if not secret:
            raise IdentityError(
                "USER_IDENTITY_SECRET is required to verify HS256 identity tokens"
            )
        return secret
    if alg == _DEFAULT_ALG_RS:
        # For verification, prefer the public key; fall back to extracting from the
        # private key (useful in single-host deployments).
        pub = _env("USER_IDENTITY_PUBLIC_KEY")
        if pub:
            return pub
        priv = _env("USER_IDENTITY_PRIVATE_KEY")
        if priv:
            return priv
        raise IdentityError(
            "USER_IDENTITY_PUBLIC_KEY (or USER_IDENTITY_PRIVATE_KEY) is required "
            "to verify RS256 identity tokens"
        )
    raise IdentityError(f"Unsupported USER_IDENTITY_ALG: {alg!r}")
