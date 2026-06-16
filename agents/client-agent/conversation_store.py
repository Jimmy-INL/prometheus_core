"""Conversation state persistence for the client-agent."""

import json
from typing import Any, Dict, Optional

import redis
from prometheus_api.redis_utils import create_redis_client

_conversation_store_client: Optional[redis.Redis] = None


def _get_conversation_store_client() -> redis.Redis:
    """Get or create the singleton Redis client for conversation storage."""
    global _conversation_store_client
    if _conversation_store_client is None:
        _conversation_store_client = create_redis_client(ping=False)
        if _conversation_store_client is None:
            raise RuntimeError("Redis client could not be created; check REDIS_URL/REDIS_PASSWORD")
    return _conversation_store_client


def store_conversation(conv_id: str, state: Dict[str, Any]) -> None:
    """Persist a conversation state document."""
    _get_conversation_store_client().set(
        f"conversation:{conv_id}",
        json.dumps(state, default=str),
    )


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    """Load a conversation state document."""
    data = _get_conversation_store_client().get(f"conversation:{conv_id}")
    return json.loads(data) if data else None
