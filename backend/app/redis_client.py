"""The backend's one ``redis.asyncio`` client, shared by every cross-worker subsystem.

Four subsystems need state shared across workers once the backend runs more than one,
and they all use the same Valkey/Redis instance:

- :mod:`app.sessions` — per-login session state (``session:{sid}``)
- :class:`app.services.events.EventBus` — SSE fan-out (``sse:{sid}`` pub/sub)
- :mod:`app.security` — logout revocation (``revoked:sid:{sid}``)
- :mod:`app.task_events` — background-task progress/results published by the client-agent

They share **one** connection pool, created in the ``app/main.py`` lifespan and reachable
as ``request.app.state.redis`` (or via :func:`get_redis` as a FastAPI dependency).

This replaces the per-call clients that :mod:`app.task_events` used to build and
``aclose()`` in ``finally`` -- a TCP connect and teardown on every Redis round trip. The
synchronous :class:`app.conversation_state.ConversationStateClient` keeps its own client,
wrapped in ``asyncio.to_thread``, for the occasional history read it owns.

``decode_responses=True`` throughout: every value the backend stores is text (JSON or a
plain scalar), so callers never see ``bytes``.
"""

from __future__ import annotations

from typing import Any, cast

import redis.asyncio as aioredis
from fastapi import Request

from app.config import settings

RedisClient = aioredis.Redis


def create_client(url: str | None = None) -> RedisClient:
    """Build a pooled client for ``url`` (default: the configured Valkey).

    ``settings.redis_url`` is already the single resolution point for the URL and
    ``REDIS_PASSWORD`` (see ``config._redis_url``), so nothing else derives it.
    """
    return cast(
        RedisClient,
        aioredis.from_url(url or settings.redis_url, decode_responses=True, socket_connect_timeout=5),
    )


def get_redis(request: Request) -> RedisClient:
    """Dependency/helper: the shared client off app state.

    Tests that drive a router through ``TestClient`` set ``app.state.redis`` to a
    ``fakeredis.aioredis.FakeRedis`` the same way they set ``app.state.session_store``.
    """
    return cast(RedisClient, request.app.state.redis)


async def close_pubsub(pubsub: Any, channel: str) -> None:
    """Best-effort teardown of one subscription: unsubscribe, then return its connection.

    Cleanup only, so a failure (the connection already gone) is swallowed.
    """
    for close in (lambda: pubsub.unsubscribe(channel), pubsub.aclose):
        try:
            await close()
        except Exception:  # noqa: BLE001 - cleanup only
            pass
