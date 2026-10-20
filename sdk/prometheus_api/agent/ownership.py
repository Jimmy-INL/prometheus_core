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

"""Conversation ownership: bind conversation_id → user_id and enforce access control.

Each conversation is owned by the user who created it.  The ownership record is
written on first touch and checked on every subsequent access to prevent one
authenticated user from reading or modifying another user's data.

Redis key schema
----------------
- ``conv_owner:{conversation_id}``   STRING  user_id (no TTL — lifetime of conv)
- ``user:convs:{user_id}``           SET     set of conversation_ids owned by user

The per-user SET enables O(N_user_convs) scoped history listing as a replacement
for the O(N_all_convs) ``keys("conversation:*")`` global scan.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Shared Redis client is obtained lazily so that modules importing this file
# do not trigger a connection attempt at import time.
_redis_client = None


def _get_redis():
    """Return the singleton Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        from prometheus_api.redis_utils import create_redis_client

        _redis_client = create_redis_client(ping=False)
    return _redis_client


def _owner_key(conversation_id: str) -> str:
    return f"conv_owner:{conversation_id}"


def _user_convs_key(user_id: str) -> str:
    return f"user:convs:{user_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_conversation_owner(conversation_id: str, user_id: str) -> None:
    """Bind *conversation_id* to *user_id* as the owning principal.

    Idempotent: if the conversation is already owned it is NOT re-bound —
    the existing owner is left unchanged.  Call :func:`assert_conversation_owner`
    separately when you need to verify ownership.

    Both Redis writes are best-effort: failures are logged but never raised so
    that a Redis unavailability does not block the request.
    """
    if not conversation_id or not user_id:
        return
    try:
        r = _get_redis()
        if r is None:
            return
        # SET NX — only write if the key does not already exist.
        r.set(_owner_key(conversation_id), user_id, nx=True)
        # Add to the per-user conversation index.
        r.sadd(_user_convs_key(user_id), conversation_id)
    except Exception as exc:
        logger.warning(
            "record_conversation_owner: failed to record owner for %r: %s",
            conversation_id,
            exc,
        )


def get_conversation_owner(conversation_id: str) -> Optional[str]:
    """Return the user_id that owns *conversation_id*, or ``None`` if unknown."""
    if not conversation_id:
        return None
    try:
        r = _get_redis()
        if r is None:
            return None
        value = r.get(_owner_key(conversation_id))
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
    except Exception as exc:
        logger.warning(
            "get_conversation_owner: failed to fetch owner for %r: %s",
            conversation_id,
            exc,
        )
        return None


def assert_conversation_owner(conversation_id: str, user_id: str) -> None:
    """Raise :class:`PermissionError` if *user_id* is not the owner of *conversation_id*.

    Passes silently when:
    - The conversation has no ownership record yet (first-access case where the
      caller will write it afterward via :func:`record_conversation_owner`).
    - Redis is unavailable (degraded mode — access control is best-effort when
      the ownership store is down; the caller should still call
      :func:`record_conversation_owner` to persist once Redis recovers).

    Raises:
        PermissionError: When a *different* user_id owns the conversation.
    """
    if not conversation_id or not user_id:
        return
    owner = get_conversation_owner(conversation_id)
    if owner is None:
        # No record yet — not an error; caller will write it.
        return
    if owner != user_id:
        raise PermissionError(f"Conversation {conversation_id!r} is owned by a different user")


def list_user_conversations(user_id: str) -> List[str]:
    """Return the list of conversation_ids owned by *user_id*.

    Used to replace the global ``keys("conversation:*")`` scan for per-user
    history listing.  Returns an empty list on Redis unavailability.
    """
    if not user_id:
        return []
    try:
        r = _get_redis()
        if r is None:
            return []
        members = r.smembers(_user_convs_key(user_id))
        return [m.decode("utf-8") if isinstance(m, bytes) else m for m in (members or [])]
    except Exception as exc:
        logger.warning("list_user_conversations: failed for user %r: %s", user_id, exc)
        return []
