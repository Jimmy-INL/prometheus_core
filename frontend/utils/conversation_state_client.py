"""Redis-backed client for browsing persisted conversation state."""

import json
from typing import Any, Dict, List

try:
    import redis
except ImportError:
    redis = None


class ConversationStateClient:
    """Read-only client for persisted conversation state."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client = None

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if redis is None:
            return None
        try:
            self._client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            self._client.ping()
            return self._client
        except Exception:
            self._client = None
            return None

    @property
    def available(self) -> bool:
        return self.client is not None

    def get_conversation_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent conversation summaries from Redis."""
        client = self.client
        if client is None:
            return []
        try:
            keys = client.keys("conversation:*")
            conversations = []
            for key in keys[:limit]:
                data = client.get(key)
                if not data:
                    continue
                conv = json.loads(data)
                conv_id = key.split(":", 1)[1] if ":" in key else key
                history = conv.get("conversation_history", []) or []
                latest_entry = history[-1] if history else {}
                conversations.append({
                    "conversation_id": conv_id,
                    "query": conv.get("user_query", ""),
                    "status": self._infer_status(conv),
                    "material_id": conv.get("material_id"),
                    "timestamp": latest_entry.get("timestamp", ""),
                })
            conversations.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
            return conversations
        except Exception:
            return []

    @staticmethod
    def _infer_status(conversation: Dict[str, Any]) -> str:
        """Infer a user-facing status from persisted state."""
        if conversation.get("final_report"):
            return "completed"
        if conversation.get("awaiting_approval"):
            return "plan_ready"
        if conversation.get("missing_info"):
            return "needs_info"
        if conversation.get("routing_decision"):
            return "executing"
        return "unknown"
