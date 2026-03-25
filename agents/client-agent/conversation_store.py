"""Conversation state persistence for the client-agent."""

import json
import os
from typing import Any, Dict, Optional

import redis

_conversation_store_client: Optional[redis.Redis] = None


def _get_conversation_store_client() -> redis.Redis:
    """Get or create the singleton Redis client for conversation storage."""
    global _conversation_store_client
    if _conversation_store_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_password = os.getenv("REDIS_PASSWORD")
        _conversation_store_client = redis.Redis.from_url(
            redis_url,
            password=redis_password,
            decode_responses=True
        )
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
