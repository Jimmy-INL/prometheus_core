"""Unit tests for app.identity -- the backend's identity-minting helper.

Covers only the backend-side wrapper (configured/unconfigured, mint failure
degrades to None rather than raising). Full mint/verify round-trip coverage
lives in prometheus_api's own test_identity.py.
"""

from __future__ import annotations

from app import identity


def test_unconfigured_returns_none(monkeypatch):
    monkeypatch.delenv("USER_IDENTITY_SECRET", raising=False)
    monkeypatch.delenv("USER_IDENTITY_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("USER_IDENTITY_ALG", "HS256")

    assert identity.mint_for_user("alice") is None


def test_empty_user_id_returns_none(monkeypatch):
    monkeypatch.setenv("USER_IDENTITY_SECRET", "test-secret")
    assert identity.mint_for_user("") is None


def test_hs256_configured_mints_a_token(monkeypatch):
    monkeypatch.setenv("USER_IDENTITY_ALG", "HS256")
    monkeypatch.setenv("USER_IDENTITY_SECRET", "test-secret-value")

    token = identity.mint_for_user("alice")
    assert token is not None
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


def test_rs256_requires_private_key_not_secret(monkeypatch):
    monkeypatch.setenv("USER_IDENTITY_ALG", "RS256")
    monkeypatch.delenv("USER_IDENTITY_PRIVATE_KEY", raising=False)
    # A stray HS256 secret must not satisfy the RS256 configuration check.
    monkeypatch.setenv("USER_IDENTITY_SECRET", "irrelevant-for-rs256")

    assert identity._is_configured() is False
    assert identity.mint_for_user("alice") is None


def test_mint_failure_returns_none_not_raise(monkeypatch):
    """Even when configured, a mint-time failure must degrade to None."""
    monkeypatch.setenv("USER_IDENTITY_ALG", "HS256")
    monkeypatch.setenv("USER_IDENTITY_SECRET", "test-secret")

    def _boom(user_id, ttl_seconds=None):
        raise RuntimeError("boom")

    import prometheus_api.agent.identity as upstream_identity

    monkeypatch.setattr(upstream_identity, "mint_user_token", _boom)

    assert identity.mint_for_user("alice") is None
