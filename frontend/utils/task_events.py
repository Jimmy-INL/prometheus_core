"""Async Redis pub/sub helpers for background-task notifications.

When the client-agent detaches a slow turn it returns a ``backgrounded`` status
and keeps the orchestration running; on completion it publishes a state-change
event on ``tasks:events:{conversation_id}`` and persists the final response under
``tasks:result:{conversation_id}:{task_id}``. The frontend subscribes here and
renders the result out-of-band when the task finishes.

Uses ``redis.asyncio`` so the listener never blocks the Chainlit event loop.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

try:  # redis.asyncio ships with redis-py >= 4.2
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover - only when redis is absent
    aioredis = None  # type: ignore

logger = logging.getLogger(__name__)

TERMINAL_STATES = frozenset({"completed", "failed", "canceled", "rejected"})


def events_channel(conversation_id: str) -> str:
    return f"tasks:events:{conversation_id}"


def _node_key(conversation_id: str, task_id: str) -> str:
    return f"tasks:node:{conversation_id}:{task_id}"


def _result_key(conversation_id: str, task_id: str) -> str:
    return f"tasks:result:{conversation_id}:{task_id}"


def is_terminal(state: Optional[str]) -> bool:
    return str(state or "") in TERMINAL_STATES


async def _get_json(client: Any, key: str) -> Optional[Dict[str, Any]]:
    try:
        data = await client.get(key)
    except Exception as exc:
        logger.warning("[TASKEVENTS] get %s failed: %s", key, exc)
        return None
    if not data:
        return None
    try:
        parsed: Dict[str, Any] = json.loads(data)
        return parsed
    except Exception:
        return None


async def fetch_result(redis_url: str, conversation_id: str, task_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the persisted final response payload for a completed task."""
    if aioredis is None:
        return None
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        return await _get_json(client, _result_key(conversation_id, task_id))
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def wait_for_task(redis_url: str, conversation_id: str, task_id: str) -> Optional[str]:
    """Block until ``task_id`` reaches a terminal state; return that state.

    Returns ``None`` if Redis is unavailable. Guards the subscribe race by
    checking the current node state immediately after subscribing, so a task
    that finishes between detach and subscribe is still detected.
    """
    if aioredis is None:
        return None
    client = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(events_channel(conversation_id))

        node = await _get_json(client, _node_key(conversation_id, task_id))
        if node and is_terminal(node.get("state")):
            return str(node.get("state"))

        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except Exception:
                continue
            if event.get("task_id") != task_id:
                continue
            if is_terminal(event.get("state")):
                return str(event.get("state"))
        return None
    finally:
        for close in (
            lambda: pubsub.unsubscribe(events_channel(conversation_id)),
            pubsub.aclose,
            client.aclose,
        ):
            try:
                await close()
            except Exception:
                pass
