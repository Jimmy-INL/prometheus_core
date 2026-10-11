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

"""HashiCorp Vault credential broker.

Authenticates to Vault using the **JWT auth method** (workload + user token),
then fetches per-user, per-resource credentials from a configured secret path.

Authentication is two-factor:
1. **JWT auth** — the *user's* platform JWT is exchanged for a Vault token
   via ``POST /auth/{mount}/login``.  Vault maps the ``sub`` claim to a
   per-user entity and policy.
2. **Workload secret** (optional) — a per-agent static secret header
   (``VAULT_AGENT_SECRET``) or mTLS client certificate (``VAULT_MTLS_*``)
   passed to the Vault HTTP client, further restricting which agents can
   exchange tokens.

Vault token caching: tokens are cached *per user_id* for up to
``min(token.lease_duration / 2, MAX_TOKEN_CACHE_TTL_SECONDS)`` seconds so
that a single turn does not make multiple Vault round-trips.  The cache is
per-process, in-memory only (``dict[user_id -> (vault_token, expires_at)]``).
No cached value is ever written to Redis or disk.

Config env vars
---------------
- ``VAULT_ADDR``          — Vault server URL (required)
- ``VAULT_JWT_MOUNT``     — JWT auth mount path (default: ``jwt``)
- ``VAULT_JWT_ROLE``      — JWT auth role name (required)
- ``VAULT_AGENT_SECRET``  — static workload-auth header value (optional)
- ``VAULT_MTLS_CERT``     — path to PEM client cert (optional, mTLS)
- ``VAULT_MTLS_KEY``      — path to PEM client key (optional, mTLS)
- ``VAULT_MTLS_CA``       — path to CA cert for server-cert validation (optional)
- ``VAULT_NAMESPACE``     — Vault namespace (optional, for HCP/Enterprise)
- ``VAULT_DEEPLYNX_PATH`` — KV path template for DeepLynx credentials
    (default: ``secret/data/deeplynx/{user_id}``)
- ``VAULT_SLURM_PATH``    — KV path template for SLURM credentials
    (default: ``secret/data/slurm/{user_id}``)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .broker import Credential, CredentialError, CredentialRequest

logger = logging.getLogger(__name__)

# Max seconds a Vault token stays in the in-process cache.
MAX_TOKEN_CACHE_TTL_SECONDS = 300


class VaultCredentialBroker:
    """Vault-backed credential broker with JWT auth and per-user policy."""

    def __init__(self) -> None:
        # In-process per-user token cache: user_id → (vault_token, expires_at)
        self._token_cache: Dict[str, Tuple[str, datetime]] = {}
        self._cache_lock = asyncio.Lock()

    async def get_credential(
        self,
        req: CredentialRequest,
        *,
        user_token: str,
    ) -> Credential:
        """Issue a short-lived credential for *req.resource* on behalf of *req.user_id*.

        Raises:
            CredentialError: On missing config, Vault auth failure, or secret lookup failure.
        """
        if not user_token:
            raise CredentialError("user_token is required for VaultCredentialBroker")

        vault_addr = os.getenv("VAULT_ADDR", "").strip()
        if not vault_addr:
            raise CredentialError("VAULT_ADDR is required for VaultCredentialBroker")

        vault_token = await self._get_vault_token(req.user_id, user_token, vault_addr)
        return await self._fetch_credential(req, vault_token, vault_addr)

    # ------------------------------------------------------------------
    # Vault token exchange (JWT auth → Vault token)
    # ------------------------------------------------------------------

    async def _get_vault_token(
        self, user_id: str, user_token: str, vault_addr: str
    ) -> str:
        """Return a cached or freshly-minted Vault token for *user_id*."""
        async with self._cache_lock:
            cached = self._token_cache.get(user_id)
            if cached:
                vault_token, expires_at = cached
                if datetime.now(timezone.utc) < expires_at:
                    return vault_token
            vault_token, ttl = await self._exchange_jwt_for_vault_token(
                user_token, vault_addr
            )
            cache_ttl = min(ttl // 2, MAX_TOKEN_CACHE_TTL_SECONDS)
            self._token_cache[user_id] = (
                vault_token,
                datetime.now(timezone.utc) + timedelta(seconds=max(cache_ttl, 0)),
            )
            return vault_token

    async def _exchange_jwt_for_vault_token(
        self, user_token: str, vault_addr: str
    ) -> Tuple[str, int]:
        """Exchange the platform JWT for a Vault token via the JWT auth method.

        Returns:
            (vault_token, lease_duration_seconds)
        """
        import httpx

        mount = os.getenv("VAULT_JWT_MOUNT", "jwt").strip()
        role = os.getenv("VAULT_JWT_ROLE", "").strip()
        if not role:
            raise CredentialError("VAULT_JWT_ROLE is required")

        namespace = os.getenv("VAULT_NAMESPACE", "").strip()
        headers: Dict[str, str] = {}
        if namespace:
            headers["X-Vault-Namespace"] = namespace
        agent_secret = os.getenv("VAULT_AGENT_SECRET", "").strip()
        if agent_secret:
            headers["X-Vault-Agent-Secret"] = agent_secret

        cert = _mtls_cert()
        verify = _mtls_ca() or True

        url = f"{vault_addr.rstrip('/')}/v1/auth/{mount}/login"
        payload = {"role": role, "jwt": user_token}

        try:
            async with httpx.AsyncClient(cert=cert, verify=verify, timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise CredentialError(
                f"Vault JWT auth failed ({exc.response.status_code}): "
                f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise CredentialError(f"Vault JWT auth request failed: {exc}") from exc

        auth = data.get("auth")
        if not isinstance(auth, dict):
            raise CredentialError("Vault JWT auth response missing 'auth' field")
        token = auth.get("client_token")
        if not token:
            raise CredentialError("Vault JWT auth response missing client_token")
        ttl = int(auth.get("lease_duration") or 0)
        return str(token), ttl

    # ------------------------------------------------------------------
    # Secret path fetching (Vault token → per-resource credential)
    # ------------------------------------------------------------------

    async def _fetch_credential(
        self, req: CredentialRequest, vault_token: str, vault_addr: str
    ) -> Credential:
        """Read the per-user secret for *req.resource* from Vault KV."""
        import httpx

        path_template = _resource_path_template(req.resource)
        if not path_template:
            raise CredentialError(f"Unknown resource {req.resource!r} for VaultCredentialBroker")

        path = path_template.format(user_id=req.user_id, **req.scope)
        namespace = os.getenv("VAULT_NAMESPACE", "").strip()
        headers: Dict[str, str] = {
            "X-Vault-Token": vault_token,
        }
        if namespace:
            headers["X-Vault-Namespace"] = namespace

        cert = _mtls_cert()
        verify = _mtls_ca() or True
        url = f"{vault_addr.rstrip('/')}/v1/{path}"

        try:
            async with httpx.AsyncClient(cert=cert, verify=verify, timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise CredentialError(
                f"Vault secret read failed ({exc.response.status_code}): "
                f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise CredentialError(f"Vault secret read request failed: {exc}") from exc

        # KV v2 wraps data in data.data; KV v1 has it directly in data.data.
        secret_data: Dict[str, Any] = {}
        raw_data = data.get("data")
        if isinstance(raw_data, dict):
            nested = raw_data.get("data")
            secret_data = nested if isinstance(nested, dict) else raw_data

        if not secret_data:
            raise CredentialError(
                f"No credential data found at Vault path {path!r} for user {req.user_id!r}"
            )

        # Determine expiry from Vault metadata if available.
        expires_at: datetime
        try:
            meta = data.get("data", {}).get("metadata", {})
            custom_ttl = int(meta.get("custom_metadata", {}).get("ttl_seconds") or 0)
        except Exception:
            custom_ttl = 0
        if custom_ttl > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=custom_ttl)
        else:
            # Fallback: honour the Vault lease_duration if present, else 1h.
            lease = int(data.get("lease_duration") or 0)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(lease, 3600))

        return Credential(resource=req.resource, value=secret_data, expires_at=expires_at)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mtls_cert():
    """Return (cert_path, key_path) tuple for mTLS, or None."""
    cert = os.getenv("VAULT_MTLS_CERT", "").strip()
    key = os.getenv("VAULT_MTLS_KEY", "").strip()
    if cert and key:
        return (cert, key)
    return None


def _mtls_ca():
    """Return CA path for server-cert verification, or None."""
    ca = os.getenv("VAULT_MTLS_CA", "").strip()
    return ca or None


def _resource_path_template(resource: str) -> Optional[str]:
    """Return the Vault KV path template for *resource*."""
    env_map = {
        "deeplynx": "VAULT_DEEPLYNX_PATH",
        "slurm": "VAULT_SLURM_PATH",
    }
    default_map = {
        "deeplynx": "secret/data/deeplynx/{user_id}",
        "slurm": "secret/data/slurm/{user_id}",
    }
    env_key = env_map.get(resource)
    if env_key:
        custom = os.getenv(env_key, "").strip()
        if custom:
            return custom
    return default_map.get(resource)
