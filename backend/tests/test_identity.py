"""Unit tests for app.identity -- the backend's identity-minting helper (RS256-only).

Covers only the backend-side wrapper (configured/unconfigured, mint failure
degrades to None rather than raising). Full mint/verify round-trip coverage
lives in prometheus_api's own test_identity.py.
"""

from __future__ import annotations

import pytest

from app import identity


@pytest.fixture(scope="module")
def rsa_private_key_pem() -> str:
    """One RSA private key (PEM) shared across tests in this module."""
    from prometheus_api.agent.identity_keygen import generate_keypair

    private_pem, _ = generate_keypair(key_size=2048)
    return private_pem


def test_unconfigured_returns_none(monkeypatch):
    monkeypatch.delenv("USER_IDENTITY_PRIVATE_KEY", raising=False)
    assert identity.mint_for_user("alice") is None


def test_empty_user_id_returns_none(monkeypatch, rsa_private_key_pem):
    monkeypatch.setenv("USER_IDENTITY_PRIVATE_KEY", rsa_private_key_pem)
    assert identity.mint_for_user("") is None


def test_configured_mints_a_token(monkeypatch, rsa_private_key_pem):
    monkeypatch.setenv("USER_IDENTITY_PRIVATE_KEY", rsa_private_key_pem)

    token = identity.mint_for_user("alice")
    assert token is not None
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


def test_mint_failure_returns_none_not_raise(monkeypatch, rsa_private_key_pem):
    """Even when configured, a mint-time failure must degrade to None."""
    monkeypatch.setenv("USER_IDENTITY_PRIVATE_KEY", rsa_private_key_pem)

    def _boom(user_id, ttl_seconds=None):
        raise RuntimeError("boom")

    import prometheus_api.agent.identity as upstream_identity

    monkeypatch.setattr(upstream_identity, "mint_user_token", _boom)

    assert identity.mint_for_user("alice") is None
