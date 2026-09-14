"""Unit tests for app.signing_keys -- kid computation, JWK conversion, keygen,
and the active-key cache used by app/identity.py."""

from __future__ import annotations

import pytest

from app import signing_keys
from app.db.models import SigningKey


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    from prometheus_api.agent.identity_keygen import generate_keypair

    return generate_keypair(key_size=2048)


def test_compute_kid_is_deterministic(rsa_keypair):
    _, public_pem = rsa_keypair
    assert signing_keys.compute_kid(public_pem) == signing_keys.compute_kid(public_pem)


def test_compute_kid_differs_for_different_keys():
    from prometheus_api.agent.identity_keygen import generate_keypair

    _, pub_a = generate_keypair(key_size=2048)
    _, pub_b = generate_keypair(key_size=2048)
    assert signing_keys.compute_kid(pub_a) != signing_keys.compute_kid(pub_b)


def test_jwk_for_has_expected_shape(rsa_keypair):
    _, public_pem = rsa_keypair
    kid = signing_keys.compute_kid(public_pem)
    key = SigningKey(kid=kid, private_key_encrypted=b"unused-in-this-test", public_key_pem=public_pem)

    jwk = signing_keys.jwk_for(key)
    assert jwk["kty"] == "RSA"
    assert jwk["use"] == "sig"
    assert jwk["alg"] == "RS256"
    assert jwk["kid"] == kid
    assert "n" in jwk and "e" in jwk
    assert "d" not in jwk  # public JWK only -- never the private exponent


def test_generate_signing_key_round_trips_kid():
    kid, private_pem, public_pem = signing_keys.generate_signing_key()
    assert kid == signing_keys.compute_kid(public_pem)
    assert "BEGIN PRIVATE KEY" in private_pem or "BEGIN RSA PRIVATE KEY" in private_pem
    assert "BEGIN PUBLIC KEY" in public_pem


# --------------------------------------------------------------------------- #
# Active-key cache
# --------------------------------------------------------------------------- #


def test_cache_starts_stale(monkeypatch):
    signing_keys.invalidate_active_key_cache()
    is_fresh, _ = signing_keys.cached_active_key()
    assert is_fresh is False


def test_cache_set_then_read():
    signing_keys.set_cached_active_key(("kid-1", "pem-1"))
    is_fresh, value = signing_keys.cached_active_key()
    assert is_fresh is True
    assert value == ("kid-1", "pem-1")


def test_cache_can_hold_a_confirmed_none():
    """A fresh cached `None` means "confirmed no active key" -- distinct from
    "cache not populated yet" (is_fresh False)."""
    signing_keys.set_cached_active_key(None)
    is_fresh, value = signing_keys.cached_active_key()
    assert is_fresh is True
    assert value is None


def test_invalidate_makes_the_cache_stale_again():
    signing_keys.set_cached_active_key(("kid-1", "pem-1"))
    signing_keys.invalidate_active_key_cache()
    is_fresh, _ = signing_keys.cached_active_key()
    assert is_fresh is False
