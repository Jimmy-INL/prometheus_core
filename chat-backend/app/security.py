"""Authentication: password identity provider, JWT cookie issue/verify, deps.

Ports ``auth_callback`` / ``oauth_callback`` from ``frontend/main.py``. Chainlit's
password auth becomes an explicit :class:`PasswordIdentityProvider`; its OAuth
pass-through becomes a modeled-but-unimplemented :class:`IdentityProvider` shape
(the callback route is reserved and stubs 501 until a real OAuth provider lands).

The session cookie is a signed JWT (``pyjwt``, ``settings.jwt_secret``). Its claims
carry the username (``sub``), ``role``, a per-login session id (``sid``), and an
``exp``. The ``sid`` is the key into the in-memory :class:`~app.sessions.SessionStore`.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol, runtime_checkable

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings

# JWT signing algorithm. HS256 is symmetric — the same ``jwt_secret`` signs and
# verifies, which matches the single-service deployment here.
_JWT_ALG = "HS256"


class User(BaseModel):
    """Authenticated principal, mirroring Chainlit's ``cl.User`` shape.

    ``identifier`` matches what the React app read from ``/user``; ``role`` and
    ``provider`` mirror the ``cl.User.metadata`` keys set in ``auth_callback``.
    """

    identifier: str
    role: str = "user"
    provider: str = "credentials"


class TokenClaims(BaseModel):
    """Decoded JWT payload."""

    sub: str
    role: str
    sid: str
    provider: str = "credentials"
    exp: int


# --------------------------------------------------------------------------- #
# Identity provider interface
# --------------------------------------------------------------------------- #


@runtime_checkable
class IdentityProvider(Protocol):
    """Pluggable auth backend.

    ``authenticate`` handles credential-based login (password today); ``callback``
    handles a redirect-based OAuth handshake (reserved — only the password provider
    is implemented, so its ``callback`` raises). Modeling both now keeps the future
    OAuth provider a drop-in.
    """

    name: str

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Return a :class:`User` on valid credentials, else ``None``."""
        ...

    def callback(self, provider_id: str, raw_user_data: dict[str, Any]) -> Optional[User]:
        """Complete a redirect-based (OAuth) handshake. Reserved."""
        ...


class PasswordIdentityProvider:
    """Local-users password check (ported from ``auth_callback``).

    Compares against ``settings.local_users`` with a constant-time
    :func:`hmac.compare_digest` so the password check isn't timing-attackable (AU-3).
    Passwords are still stored in cleartext in ``config.yml`` — a **dev-only**
    mechanism carried over from Chainlit; production auth should go through a real
    identity provider (see :func:`get_provider` / the OAuth seam). Hashed-at-rest
    storage is a deferred follow-up (needs a hashing dependency + a config migration).
    """

    name = "credentials"

    def authenticate(self, username: str, password: str) -> Optional[User]:
        for user in settings.local_users:
            if user.get("username") == username and hmac.compare_digest(
                str(user.get("password") or ""), str(password or "")
            ):
                return User(
                    identifier=username,
                    role=user.get("role", "user"),
                    provider=self.name,
                )
        return None

    def callback(self, provider_id: str, raw_user_data: dict[str, Any]) -> Optional[User]:
        raise NotImplementedError("Password provider has no redirect callback")


# The active credential provider. Swap/extend when OAuth arrives.
password_provider = PasswordIdentityProvider()

# Provider registry (AU-6): a real seam rather than a hardcoded singleton. Login and
# the OAuth callback resolve providers through here, and a future OAuth provider is a
# drop-in via :func:`register_provider`. Only the password provider is wired today.
_PROVIDERS: dict[str, "IdentityProvider"] = {password_provider.name: password_provider}


def register_provider(provider: "IdentityProvider") -> None:
    """Register (or replace) an identity provider by its ``name``."""
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> Optional["IdentityProvider"]:
    """Return the identity provider for ``name``, or ``None`` if unregistered."""
    return _PROVIDERS.get(name)


# --------------------------------------------------------------------------- #
# Session revocation (AU-1) — logout invalidates the JWT before its natural expiry
# --------------------------------------------------------------------------- #

# Process-local {sid: token-exp-epoch}. Lost on restart — same volatility as
# SessionStore. On logout the session's sid is revoked so a retained cookie stops
# passing ``current_claims`` before ``exp`` (the JWT itself is stateless).
_revoked_sids: dict[str, int] = {}


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def revoke_session(sid: str, exp: int) -> None:
    """Revoke a session id until ``exp`` (its token's expiry).

    Prunes already-expired entries first so the set can't grow without bound.
    """
    now = _now_epoch()
    for dead in [s for s, e in _revoked_sids.items() if e <= now]:
        _revoked_sids.pop(dead, None)
    _revoked_sids[sid] = exp


def is_revoked(sid: str) -> bool:
    exp = _revoked_sids.get(sid)
    if exp is None:
        return False
    if exp <= _now_epoch():
        _revoked_sids.pop(sid, None)  # expired anyway — drop and treat as not revoked
        return False
    return True


# --------------------------------------------------------------------------- #
# JWT issue / verify
# --------------------------------------------------------------------------- #


def issue_token(user: User, sid: Optional[str] = None) -> str:
    """Sign a JWT for ``user``. Mints a fresh ``sid`` unless one is supplied."""
    if not settings.jwt_secret:
        # Fail loud rather than sign with an empty key (which would make forgery trivial).
        raise RuntimeError("jwt_secret is not configured (set CHAT_BACKEND_JWT_SECRET or CHAINLIT_AUTH_SECRET)")
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user.identifier,
        "role": user.role,
        "provider": user.provider,
        "sid": sid or str(uuid.uuid4()),
        "exp": now + timedelta(seconds=settings.token_ttl_seconds),
        "iat": now,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_JWT_ALG)


def verify_token(token: str) -> TokenClaims:
    """Decode and validate a JWT. Raises ``jwt.InvalidTokenError`` on any failure."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALG])
    return TokenClaims(**payload)


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #


def current_claims(session_cookie: Optional[str] = Cookie(default=None, alias=settings.cookie_name)) -> TokenClaims:
    """Dependency: verify the session cookie and return its claims, or 401.

    ``alias`` binds this to the configured cookie name; the parameter name itself
    is arbitrary.
    """
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = verify_token(session_cookie)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from exc
    if is_revoked(claims.sid):  # AU-1: logged-out sessions are rejected before exp
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been logged out")
    return claims


def current_user(claims: TokenClaims = Depends(current_claims)) -> User:
    """Dependency: the authenticated :class:`User` derived from the cookie."""
    return User(identifier=claims.sub, role=claims.role, provider=claims.provider)
