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

"""Shared helpers for the admin-plane RS256 signing keys (app/db/models.py::SigningKey).

Used by:
- app/routers/admin_keys.py -- generate/activate/retire admin actions
- app/routers/jwks.py -- the public JWKS document
- app/identity.py -- DB-first active-key lookup for minting, with a short cache
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional, cast

from app.db.models import SigningKey


def _jwk_dict(public_key_pem: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from jwt.algorithms import RSAAlgorithm

    public_key = load_pem_public_key(public_key_pem.encode())
    if not isinstance(public_key, RSAPublicKey):
        # Every key this module ever writes comes from generate_signing_key()
        # (always RSA) -- a non-RSA PEM here means a row was hand-edited or
        # corrupted, not a case to silently coerce.
        raise ValueError(f"Expected an RSA public key, got {type(public_key).__name__}")
    return cast(dict[str, Any], json.loads(RSAAlgorithm.to_jwk(public_key)))


def compute_kid(public_key_pem: str) -> str:
    """SHA-256 thumbprint of the JWK modulus, truncated to 16 hex chars.

    Matches ``prometheus_api.agent.identity._compute_kid()``'s algorithm exactly,
    so a kid computed here lines up with one computed there if this same key is
    ever also placed in ``USER_IDENTITY_PUBLIC_KEY`` for a bootstrap/fallback
    deployment -- not required for correctness (the DB is the source of truth
    for its own keys), just for a kid to mean the same thing everywhere.
    """
    jwk = _jwk_dict(public_key_pem)
    return hashlib.sha256(jwk["n"].encode()).hexdigest()[:16]


def jwk_for(key: SigningKey) -> dict[str, Any]:
    """This key's public half as an RFC 7517 JWK entry."""
    jwk = _jwk_dict(key.public_key_pem)
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwk["kid"] = key.kid
    return jwk


def generate_signing_key() -> tuple[str, str, str]:
    """Return ``(kid, private_key_pem, public_key_pem)`` for a fresh RS256 keypair.

    ``prometheus_api.agent.identity_keygen.generate_keypair()`` ships in the
    base image the backend already depends on.
    """
    from prometheus_api.agent.identity_keygen import generate_keypair

    private_pem, public_pem = generate_keypair()
    return compute_kid(public_pem), private_pem, public_pem


# --------------------------------------------------------------------------- #
# Active-key cache for minting (app/identity.py) -- avoids a DB round-trip on
# every mint_for_user() call. Invalidated explicitly by admin_keys.py right
# after activate/retire so a rotation takes effect immediately rather than
# waiting out the TTL below.
# --------------------------------------------------------------------------- #

_CACHE_TTL_SECONDS = 60

_cache_value: Optional[tuple[str, str]] = None  # (kid, private_key_pem)
_cache_fresh_until = 0.0  # time.monotonic() deadline; 0 means "never populated"


def cached_active_key() -> tuple[bool, Optional[tuple[str, str]]]:
    """Return ``(is_fresh, value)``. Check ``is_fresh`` before trusting ``value`` --
    a fresh ``None`` means "confirmed no active key", a stale one means "unknown, go
    reload"."""
    return time.monotonic() < _cache_fresh_until, _cache_value


def set_cached_active_key(value: Optional[tuple[str, str]]) -> None:
    global _cache_value, _cache_fresh_until
    _cache_value = value
    _cache_fresh_until = time.monotonic() + _CACHE_TTL_SECONDS


def invalidate_active_key_cache() -> None:
    global _cache_fresh_until
    _cache_fresh_until = 0.0
