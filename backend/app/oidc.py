"""OIDC authorization-code flow: discovery, token exchange, ID-token
verification, and account upsert.

Split out from ``app/security.py`` (which owns the ``GenericOidcProvider``
class itself, the ``IdentityProvider`` implementation admin_oidc.py's rows
resolve to) because this module is mostly IO/crypto plumbing, not "which
provider is this" -- keeps security.py's provider classes short and lets this
module be tested (discovery/token/verification) independent of the routing
seam.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt
from app.db.models import OidcProvider as OidcProviderRow
from app.db.models import User as UserRow

_HTTP_TIMEOUT = 10.0


class OidcError(Exception):
    """Any failure in the OIDC flow -- routers/auth.py (via security.py's
    GenericOidcProvider) turns this into a 400 response to the browser."""


async def fetch_discovery(issuer_url: str) -> dict[str, Any]:
    """Fetch ``{issuer_url}/.well-known/openid-configuration``.

    Fetched fresh on every login rather than cached -- login is not a hot
    path, and an admin editing ``issuer_url`` should take effect immediately.
    """
    url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return dict(resp.json())
    except httpx.HTTPError as exc:
        raise OidcError(f"Could not fetch OIDC discovery document from {url!r}: {exc}") from exc


def build_authorization_url(
    discovery: dict[str, Any],
    provider: OidcProviderRow,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
) -> str:
    endpoint = discovery.get("authorization_endpoint")
    if not endpoint:
        raise OidcError("Discovery document is missing authorization_endpoint")
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{endpoint}?{urlencode(params)}"


async def exchange_code(
    discovery: dict[str, Any], provider: OidcProviderRow, *, code: str, redirect_uri: str
) -> dict[str, Any]:
    endpoint = discovery.get("token_endpoint")
    if not endpoint:
        raise OidcError("Discovery document is missing token_endpoint")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": provider.client_id,
                    "client_secret": decrypt(provider.client_secret_encrypted),
                },
            )
            resp.raise_for_status()
            return dict(resp.json())
    except httpx.HTTPError as exc:
        raise OidcError(f"Token exchange with {provider.provider_id!r} failed: {exc}") from exc


def verify_id_token(
    discovery: dict[str, Any], provider: OidcProviderRow, id_token: str, *, expected_nonce: str
) -> dict[str, Any]:
    """Verify signature, exp/iat, iss, aud, and nonce. Raises :class:`OidcError`
    on any failure -- never returns unverified claims."""
    jwks_uri = discovery.get("jwks_uri")
    if not jwks_uri:
        raise OidcError("Discovery document is missing jwks_uri")
    try:
        signing_key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=provider.client_id,
            issuer=discovery.get("issuer", provider.issuer_url),
            options={"require": ["sub", "exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise OidcError(f"id_token verification failed: {exc}") from exc
    if claims.get("nonce") != expected_nonce:
        raise OidcError("id_token nonce mismatch")
    return dict(claims)


def _fallback_username(provider_id: str, external_subject: str) -> str:
    return f"{provider_id}:{external_subject}"


async def upsert_user(
    db: AsyncSession, provider: OidcProviderRow, external_subject: str, claims: dict[str, Any]
) -> UserRow:
    """Resolve verified claims to a ``users`` row -- creates one (with the
    provider's ``default_role``) on first login, refreshes email/display_name
    on subsequent ones. Raises :class:`OidcError` if the matched account has
    been deactivated.

    Keyed by ``(provider.provider_id, external_subject)`` -- the same pair the
    ``users`` table's unique constraint enforces (app/db/models.py::User).
    """
    row = await db.scalar(
        select(UserRow).where(UserRow.provider == provider.provider_id, UserRow.external_subject == external_subject)
    )
    email = claims.get("email")
    display_name = claims.get("name") or claims.get("preferred_username")
    now = datetime.now(timezone.utc)

    if row is not None:
        if not row.is_active:
            raise OidcError("This account has been deactivated")
        if email:
            row.email = email
        if display_name:
            row.display_name = display_name
        row.last_login_at = now
        await db.commit()
        return row

    fallback_username = _fallback_username(provider.provider_id, external_subject)
    candidate = claims.get("preferred_username") or email or fallback_username

    def _new_row(username: str) -> UserRow:
        return UserRow(
            username=username,
            role=provider.default_role,
            provider=provider.provider_id,
            external_subject=external_subject,
            email=email,
            display_name=display_name,
            last_login_at=now,
        )

    new_row = _new_row(candidate)
    db.add(new_row)
    try:
        await db.commit()
    except IntegrityError:
        # `candidate` (preferred_username/email) collided with an existing
        # username -- fall back to a name that's guaranteed unique given the
        # (provider, external_subject) lookup above already found no match
        # for *this* identity (a different provider's user or a local account
        # deliberately named e.g. "okta:abc123" could theoretically still
        # collide here too; not worth engineering around further).
        await db.rollback()
        new_row = _new_row(fallback_username)
        db.add(new_row)
        await db.commit()

    return new_row
