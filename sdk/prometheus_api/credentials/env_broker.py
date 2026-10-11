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

"""Fallback broker that returns credentials from environment variables.

This broker is used when ``CREDENTIAL_BROKER=env`` (the default) so that
single-developer and CI deployments without Vault keep working.

It maps each resource to a fixed set of env vars and returns them verbatim
as the credential value — exactly how the platform behaved before the
multi-user credential plane was added.

Security note: this broker does **not** enforce per-user isolation — all users
receive the same global credential.  It is intentionally lightweight and
should only be used in development or single-user deployments.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from .broker import Credential, CredentialBroker, CredentialError, CredentialRequest


class EnvCredentialBroker:
    """Return environment-variable credentials for every user, no per-user isolation."""

    # Each resource maps to a factory that builds the credential value dict
    # from environment variables.  Raise CredentialError if required vars are
    # missing.
    _RESOURCE_FACTORIES: Dict[str, Any] = {}

    async def get_credential(
        self,
        req: CredentialRequest,
        *,
        user_token: str,
    ) -> Credential:
        """Return an env-variable credential for *req.resource*.

        The ``user_token`` parameter is accepted but ignored — the env broker
        does not verify identity or enforce per-user policy.
        """
        factory = self._RESOURCE_FACTORIES.get(req.resource)
        if factory is None:
            factory = _fallback_factory
        value = factory(req)
        # Env credentials don't expire — use a far future datetime.
        expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        return Credential(resource=req.resource, value=value, expires_at=expires_at)


def _fallback_factory(req: CredentialRequest) -> Dict[str, Any]:
    """Return empty dict for unknown resources (graceful degradation)."""
    return {}


def _deeplynx_factory(req: CredentialRequest) -> Dict[str, Any]:
    jwt_token = os.getenv("DEEPLYNX_JWT_TOKEN", "").strip()
    key = os.getenv("DEEPLYNX_KEY", "").strip()
    secret = os.getenv("DEEPLYNX_SECRET", "").strip()
    if not jwt_token and not (key and secret):
        raise CredentialError(
            "DeepLynx credentials not configured: set DEEPLYNX_JWT_TOKEN or "
            "DEEPLYNX_KEY + DEEPLYNX_SECRET"
        )
    result: Dict[str, Any] = {}
    if jwt_token:
        result["jwt_token"] = jwt_token
    if key:
        result["key"] = key
    if secret:
        result["secret"] = secret
    # Include org/project from env so callers can build ConnectionConfig.
    org_id = os.getenv("DEEPLYNX_ORG_ID", "").strip()
    proj_id = os.getenv("DEEPLYNX_PROJECT_ID", "").strip()
    if org_id:
        result["org_id"] = org_id
    if proj_id:
        result["project_id"] = proj_id
    return result


def _slurm_factory(req: CredentialRequest) -> Dict[str, Any]:
    token = os.getenv("SLURM_JWT_TOKEN", "").strip()
    user = os.getenv("SLURM_USER", "").strip()
    url = os.getenv("SLURM_REST_URL", "").strip()
    if not token:
        raise CredentialError(
            "SLURM credentials not configured: set SLURM_JWT_TOKEN"
        )
    return {"token": token, "user": user, "slurm_rest_url": url}


EnvCredentialBroker._RESOURCE_FACTORIES = {
    "deeplynx": _deeplynx_factory,
    "slurm": _slurm_factory,
}
