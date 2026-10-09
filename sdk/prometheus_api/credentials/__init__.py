"""Credential brokering: per-user, per-resource, just-in-time credential issuance.

Agents fetch credentials from the broker at execution time rather than reading
long-lived secrets from environment variables.  Two trust factors are required:

1. **Workload authentication** — proves the *agent* is a legitimate platform
   workload (mTLS client certificate or a per-agent secret header).
2. **User assertion** — the caller forwards the user's platform JWT so the
   broker can enforce per-user policy.

Usage::

    from prometheus_api.credentials import get_broker, CredentialRequest

    broker = get_broker()
    cred = await broker.get_credential(
        CredentialRequest(user_id="alice", resource="deeplynx"),
        user_token=identity.raw_token,
    )
    # cred.value["jwt_token"] is a short-lived JWT for DeepLynx
"""

from .broker import Credential, CredentialBroker, CredentialRequest, CredentialError
from .factory import get_broker

__all__ = [
    "Credential",
    "CredentialBroker",
    "CredentialError",
    "CredentialRequest",
    "get_broker",
]
