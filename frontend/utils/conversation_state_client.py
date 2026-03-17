"""Redis-backed client for browsing persisted conversation state."""

import json
from typing import Any, Dict, List

try:
    import redis
except ImportError:
    redis = None


class ConversationStateClient:
    """Read-only client for conversation state and status history."""

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

    def get_status_history(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Retrieve status history for a conversation."""
        client = self.client
        if client is None:
            return []
        try:
            history_key = f"agent:status_history:{conversation_id}"
            history_raw = client.lrange(history_key, 0, -1)
            history = []
            for item in history_raw:
                try:
                    parsed = json.loads(item)
                    if isinstance(parsed, dict):
                        history.append(parsed)
                except Exception:
                    continue
            return history
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
