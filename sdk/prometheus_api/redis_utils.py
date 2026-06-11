"""Shared Redis connection helpers.

Every Prometheus component (artifact registry, context state, task store,
client-agent conversation/status/task-graph stores, specialist agents) needs
the same connection recipe: ``REDIS_URL`` plus an optional separate
``REDIS_PASSWORD`` (which overrides any password embedded in the URL),
``decode_responses=True``, and a fail-fast ping. This module is the single
implementation; do not copy the recipe into consumers.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379"


def redis_url_from_env() -> str:
    """Return the configured Redis URL (``REDIS_URL``, default localhost)."""
    return os.getenv("REDIS_URL") or DEFAULT_REDIS_URL


def create_redis_client(
    url: Optional[str] = None,
    *,
    password: Optional[str] = None,
    decode_responses: bool = True,
    ping: bool = True,
) -> Optional["redis.Redis"]:
    """Create a Redis client from explicit args or environment defaults.

    Args:
        url: Connection URL; defaults to ``REDIS_URL`` (or localhost).
        password: Password; defaults to ``REDIS_PASSWORD`` when set. An
            explicit/env password overrides one embedded in the URL.
        decode_responses: Decode replies to ``str`` (the platform-wide
            convention).
        ping: Ping once to fail fast on unreachable endpoints.

    Returns:
        A connected client, or ``None`` when the connection fails (callers
        with in-memory fallbacks treat ``None`` as "degraded"). The failure
        is logged so the degradation is never silent.
    """
    resolved_url = url or redis_url_from_env()
    resolved_password = password if password is not None else os.getenv("REDIS_PASSWORD")
    kwargs: dict[str, Any] = {"decode_responses": decode_responses}
    if resolved_password:
        kwargs["password"] = resolved_password
    try:
        client = redis.Redis.from_url(resolved_url, **kwargs)
        if ping:
            client.ping()
        return client
    except Exception as exc:
        logger.warning("Redis unavailable at %s: %s", resolved_url, exc)
        return None
