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

"""Broker factory: select the right backend from CREDENTIAL_BROKER env var.

Available backends:
- ``env``   (default) — reads from environment variables, no per-user isolation
- ``vault`` — HashiCorp Vault with JWT auth + per-user policy
- ``bespoke`` — placeholder; raises ImportError until a custom backend is dropped in

Example::

    from prometheus_api.credentials import get_broker
    broker = get_broker()
"""

from __future__ import annotations

import os
from typing import Optional

from .broker import CredentialBroker, CredentialError

# Singleton broker instance — created once per process.
_broker: Optional[CredentialBroker] = None


def get_broker() -> CredentialBroker:
    """Return (or lazily create) the singleton broker for this process.

    Backend selection: the ``CREDENTIAL_BROKER`` env var (case-insensitive):
    - ``"env"``     (default) — :class:`EnvCredentialBroker`
    - ``"vault"``   — :class:`VaultCredentialBroker`
    - ``"bespoke"`` — tries to import ``prometheus_api_credentials_bespoke.Broker``
    """
    global _broker
    if _broker is None:
        _broker = _create_broker()
    return _broker


def _create_broker() -> CredentialBroker:
    backend = os.getenv("CREDENTIAL_BROKER", "env").strip().lower()
    if backend in ("env", ""):
        from .env_broker import EnvCredentialBroker

        return EnvCredentialBroker()
    if backend == "vault":
        from .vault_broker import VaultCredentialBroker

        return VaultCredentialBroker()
    if backend == "bespoke":
        try:
            import importlib

            mod = importlib.import_module("prometheus_api_credentials_bespoke")
            broker: CredentialBroker = mod.Broker()
            return broker
        except ImportError as exc:
            raise CredentialError(
                "CREDENTIAL_BROKER=bespoke but the bespoke backend package "
                "'prometheus_api_credentials_bespoke' is not installed"
            ) from exc
    raise CredentialError(
        f"Unknown CREDENTIAL_BROKER value {backend!r}. Valid values: 'env', 'vault', 'bespoke'."
    )
