"""
Redis-backed memory client for browsing and managing factoids.

Connects to the same Redis instance used by the client-agent's MemoryManager,
providing read/delete access to factoids for the Chainlit UI.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import redis
except ImportError:
    redis = None


class MemoryClient:
    """Read-only client for browsing the client-agent's factoid memory."""

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

    def get_all_factoids(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve all stored factoids."""
        client = self.client
        if client is None:
            return []
        try:
            keys = client.keys("factoid:*")
            factoids = []
            for key in keys[:limit]:
                data = client.get(key)
                if data:
                    factoids.append(json.loads(data))
            factoids.sort(
                key=lambda f: f.get("created_at", ""),
                reverse=True,
            )
            return factoids
        except Exception:
            return []

    def get_factoids_by_material(self, material_id: str) -> List[Dict[str, Any]]:
        """Retrieve factoids for a specific material."""
        client = self.client
        if client is None:
            return []
        try:
            factoid_ids = client.smembers(f"material:{material_id}:factoids")
            factoids = []
            for fid in factoid_ids:
                data = client.get(f"factoid:{fid}")
                if data:
                    factoids.append(json.loads(data))
            return factoids
        except Exception:
            return []

    def delete_factoid(self, factoid_id: str) -> bool:
        """Delete a single factoid and its indexes."""
        client = self.client
        if client is None:
            return False
        try:
            data = client.get(f"factoid:{factoid_id}")
            if not data:
                return False
            factoid = json.loads(data)
            if factoid.get("material_id"):
                client.srem(f"material:{factoid['material_id']}:factoids", factoid_id)
            if factoid.get("analysis_type"):
                client.srem(f"analysis_type:{factoid['analysis_type']}:factoids", factoid_id)
            client.zrem("embeddings:index", factoid_id)
            client.delete(f"factoid:{factoid_id}")
            return True
        except Exception:
            return False

    def clear_all_factoids(self) -> int:
        """Delete all factoids. Returns count of deleted factoids."""
        client = self.client
        if client is None:
            return 0
        try:
            keys = client.keys("factoid:*")
            count = 0
            for key in keys:
                fid = key.split(":", 1)[1] if ":" in key else key
                if self.delete_factoid(fid):
                    count += 1
            return count
        except Exception:
            return 0

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
                if data:
                    conv = json.loads(data)
                    conv_id = key.split(":", 1)[1] if ":" in key else key
                    conversations.append({
                        "conversation_id": conv_id,
                        "query": conv.get("user_query", ""),
                        "status": conv.get("status", "unknown"),
                        "material_id": conv.get("material_id"),
                        "timestamp": conv.get("created_at", ""),
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
