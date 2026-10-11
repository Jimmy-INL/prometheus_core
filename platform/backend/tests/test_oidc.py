# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Unit tests for app.oidc -- discovery, token exchange, ID-token verification,
and the users-table upsert. No real network access: httpx.AsyncClient.get/post
are monkeypatched to return canned httpx.Response objects; jwt.PyJWKClient is
replaced with a stub that hands back a real (locally generated) RSA public key
so signature/iss/aud/exp/nonce verification in verify_id_token runs for real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app import oidc
from app.db.models import OidcProvider as OidcProviderRow
from app.db.models import User as UserRow


@pytest.fixture(scope="module")
def idp_keypair() -> tuple[str, str]:
    from prometheus_api.agent.identity_keygen import generate_keypair

    return generate_keypair(key_size=2048)


def _json_response(method: str, url: str, payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request(method, url))


def _provider_row(**overrides) -> OidcProviderRow:
    from app.crypto import encrypt

    defaults = dict(
        provider_id="okta",
        display_name="Okta",
        issuer_url="https://idp.example.com",
        client_id="test-client-id",
        client_secret_encrypted=encrypt("test-client-secret"),
        scopes="openid profile email",
        default_role="user",
        is_enabled=True,
    )
    defaults.update(overrides)
    return OidcProviderRow(**defaults)


# --------------------------------------------------------------------------- #
# fetch_discovery
# --------------------------------------------------------------------------- #


async def test_fetch_discovery_returns_the_document(monkeypatch):
    doc = {"authorization_endpoint": "https://idp.example.com/auth", "token_endpoint": "https://idp.example.com/token"}

    async def _get(self, url, **kwargs):
        assert url == "https://idp.example.com/.well-known/openid-configuration"
        return _json_response("GET", url, doc)

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    result = await oidc.fetch_discovery("https://idp.example.com")
    assert result == doc


async def test_fetch_discovery_strips_trailing_slash(monkeypatch):
    async def _get(self, url, **kwargs):
        assert url == "https://idp.example.com/.well-known/openid-configuration"
        return _json_response("GET", url, {})

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    await oidc.fetch_discovery("https://idp.example.com/")


async def test_fetch_discovery_raises_oidc_error_on_http_failure(monkeypatch):
    async def _get(self, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    with pytest.raises(oidc.OidcError):
        await oidc.fetch_discovery("https://idp.example.com")


# --------------------------------------------------------------------------- #
# build_authorization_url
# --------------------------------------------------------------------------- #


def test_build_authorization_url_includes_required_params():
    provider = _provider_row()
    discovery = {"authorization_endpoint": "https://idp.example.com/auth"}
    url = oidc.build_authorization_url(
        discovery, provider, redirect_uri="https://backend.example.com/api/auth/callback/okta", state="s1", nonce="n1"
    )
    assert url.startswith("https://idp.example.com/auth?")
    for fragment in ("response_type=code", "client_id=test-client-id", "state=s1", "nonce=n1"):
        assert fragment in url


def test_build_authorization_url_requires_authorization_endpoint():
    with pytest.raises(oidc.OidcError):
        oidc.build_authorization_url({}, _provider_row(), redirect_uri="https://x/callback", state="s", nonce="n")


# --------------------------------------------------------------------------- #
# exchange_code
# --------------------------------------------------------------------------- #


async def test_exchange_code_posts_expected_form_and_returns_tokens(monkeypatch):
    captured = {}

    async def _post(self, url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        return _json_response("POST", url, {"id_token": "abc", "access_token": "def"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    provider = _provider_row()
    discovery = {"token_endpoint": "https://idp.example.com/token"}

    result = await oidc.exchange_code(discovery, provider, code="the-code", redirect_uri="https://backend/cb")
    assert result == {"id_token": "abc", "access_token": "def"}
    assert captured["url"] == "https://idp.example.com/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "the-code"
    assert captured["data"]["client_secret"] == "test-client-secret"  # decrypted


async def test_exchange_code_raises_oidc_error_on_http_failure(monkeypatch):
    async def _post(self, url, **kwargs):
        return httpx.Response(400, json={"error": "invalid_grant"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    with pytest.raises(oidc.OidcError):
        await oidc.exchange_code(
            {"token_endpoint": "https://idp.example.com/token"}, _provider_row(), code="bad", redirect_uri="https://x"
        )


# --------------------------------------------------------------------------- #
# verify_id_token -- real RS256 signature/claims verification, fake JWKS fetch
# --------------------------------------------------------------------------- #


class _FakeSigningKey:
    def __init__(self, key: str) -> None:
        self.key = key


class _FakeJWKClient:
    def __init__(self, jwks_uri: str, public_key_pem: str) -> None:
        self._public_key_pem = public_key_pem

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(self._public_key_pem)


def _sign_id_token(private_pem: str, **claim_overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://idp.example.com",
        "sub": "user-123",
        "aud": "test-client-id",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "nonce": "expected-nonce",
        "email": "alice@example.com",
        "name": "Alice Example",
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


def _patch_jwks(monkeypatch, public_pem: str) -> None:
    monkeypatch.setattr(oidc, "PyJWKClient", lambda jwks_uri: _FakeJWKClient(jwks_uri, public_pem))


def test_verify_id_token_happy_path(monkeypatch, idp_keypair):
    private_pem, public_pem = idp_keypair
    _patch_jwks(monkeypatch, public_pem)
    token = _sign_id_token(private_pem)
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    claims = oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="expected-nonce")
    assert claims["sub"] == "user-123"
    assert claims["email"] == "alice@example.com"


def test_verify_id_token_rejects_nonce_mismatch(monkeypatch, idp_keypair):
    private_pem, public_pem = idp_keypair
    _patch_jwks(monkeypatch, public_pem)
    token = _sign_id_token(private_pem)
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    with pytest.raises(oidc.OidcError, match="nonce"):
        oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="a-different-nonce")


def test_verify_id_token_rejects_wrong_audience(monkeypatch, idp_keypair):
    private_pem, public_pem = idp_keypair
    _patch_jwks(monkeypatch, public_pem)
    token = _sign_id_token(private_pem, aud="someone-elses-client-id")
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    with pytest.raises(oidc.OidcError):
        oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="expected-nonce")


def test_verify_id_token_rejects_wrong_issuer(monkeypatch, idp_keypair):
    private_pem, public_pem = idp_keypair
    _patch_jwks(monkeypatch, public_pem)
    token = _sign_id_token(private_pem, iss="https://not-the-real-idp.example.com")
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    with pytest.raises(oidc.OidcError):
        oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="expected-nonce")


def test_verify_id_token_rejects_expired_token(monkeypatch, idp_keypair):
    private_pem, public_pem = idp_keypair
    _patch_jwks(monkeypatch, public_pem)
    now = datetime.now(timezone.utc)
    token = _sign_id_token(private_pem, exp=now - timedelta(minutes=5), iat=now - timedelta(minutes=10))
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    with pytest.raises(oidc.OidcError):
        oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="expected-nonce")


def test_verify_id_token_rejects_wrong_signature(monkeypatch, idp_keypair):
    """A token signed by a *different* key than the one the JWKS reports must fail."""
    from prometheus_api.agent.identity_keygen import generate_keypair

    private_pem, _ = idp_keypair
    _, attacker_public_pem = generate_keypair(key_size=2048)
    _patch_jwks(monkeypatch, attacker_public_pem)  # JWKS reports a different key than what signed the token
    token = _sign_id_token(private_pem)
    discovery = {"jwks_uri": "https://idp.example.com/jwks", "issuer": "https://idp.example.com"}

    with pytest.raises(oidc.OidcError):
        oidc.verify_id_token(discovery, _provider_row(), token, expected_nonce="expected-nonce")


def test_verify_id_token_requires_jwks_uri():
    with pytest.raises(oidc.OidcError):
        oidc.verify_id_token({}, _provider_row(), "irrelevant", expected_nonce="n")


# --------------------------------------------------------------------------- #
# upsert_user
# --------------------------------------------------------------------------- #


async def test_upsert_user_creates_new_account_with_default_role(db_session):
    provider = _provider_row(default_role="admin")
    claims = {"sub": "user-1", "email": "bob@example.com", "preferred_username": "bob"}

    row = await oidc.upsert_user(db_session, provider, "user-1", claims)
    assert row.username == "bob"
    assert row.role == "admin"
    assert row.provider == "okta"
    assert row.external_subject == "user-1"
    assert row.email == "bob@example.com"


async def test_upsert_user_is_idempotent_for_returning_user(db_session):
    provider = _provider_row()
    claims = {"sub": "user-2", "email": "carol@example.com", "preferred_username": "carol"}
    first = await oidc.upsert_user(db_session, provider, "user-2", claims)

    updated_claims = {"sub": "user-2", "email": "carol-new@example.com", "name": "Carol Updated"}
    second = await oidc.upsert_user(db_session, provider, "user-2", updated_claims)

    assert first.id == second.id
    assert second.email == "carol-new@example.com"
    assert second.display_name == "Carol Updated"


async def test_upsert_user_rejects_deactivated_account(db_session):
    provider = _provider_row()
    claims = {"sub": "user-3", "email": "dan@example.com"}
    row = await oidc.upsert_user(db_session, provider, "user-3", claims)
    row.is_active = False
    await db_session.commit()

    with pytest.raises(oidc.OidcError, match="deactivated"):
        await oidc.upsert_user(db_session, provider, "user-3", claims)


async def test_upsert_user_falls_back_to_provider_subject_username_on_collision(db_session):
    provider = _provider_row()
    # A local user already holds the username the new OIDC identity would want.
    db_session.add(UserRow(username="eve", provider="credentials", password_hash="irrelevant"))
    await db_session.commit()

    claims = {"sub": "user-4", "preferred_username": "eve"}
    row = await oidc.upsert_user(db_session, provider, "user-4", claims)
    assert row.username == "okta:user-4"


async def test_upsert_user_falls_back_to_provider_subject_when_no_claims_available(db_session):
    provider = _provider_row()
    row = await oidc.upsert_user(db_session, provider, "user-5", {"sub": "user-5"})
    assert row.username == "okta:user-5"
