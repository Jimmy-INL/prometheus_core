"""Per-agent context state persistence keyed by A2A contextId."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

try:
    import redis
except Exception:  # pragma: no cover - optional dependency in some test envs
    redis = None


class ContextStateStore:
    """Redis-backed state store with in-memory fallback.

    State is isolated by producer agent id and A2A contextId so each specialist
    can persist partial execution state across INPUT_REQUIRED round-trips.
    """

    DEFAULT_TTL_SECONDS = 24 * 3600

    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: Optional[int] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        configured_ttl = os.getenv("AGENT_CONTEXT_TTL_SECONDS", "").strip()
        ttl = ttl_seconds
        if ttl is None and configured_ttl:
            try:
                ttl = int(configured_ttl)
            except ValueError:
                ttl = None
        self.ttl_seconds = ttl if ttl is not None else self.DEFAULT_TTL_SECONDS

        self._redis = None
        self._memory_lock = threading.Lock()
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    @property
    def redis_client(self):
        if self._redis is not None:
            return self._redis
        if redis is None:
            return None
        try:
            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._redis.ping()
            return self._redis
        except Exception:
            self._redis = None
            return None

    def _key(self, agent_id: str, context_id: str) -> str:
        return f"agent_ctx:{agent_id}:{context_id}"

    def load(self, agent_id: str, context_id: str) -> Dict[str, Any]:
        agent_id = str(agent_id or "").strip()
        context_id = str(context_id or "").strip()
        if not agent_id or not context_id:
            return {}

        client = self.redis_client
        if client is not None:
            try:
                raw = client.get(self._key(agent_id, context_id))
                if raw:
                    payload = json.loads(raw)
                    return payload if isinstance(payload, dict) else {}
            except Exception:
                pass

        with self._memory_lock:
            payload = self._memory_store.get(self._key(agent_id, context_id), {})
            return dict(payload) if isinstance(payload, dict) else {}

    def save(self, agent_id: str, context_id: str, state: Dict[str, Any]) -> None:
        agent_id = str(agent_id or "").strip()
        context_id = str(context_id or "").strip()
        if not agent_id or not context_id:
            raise ValueError("agent_id and context_id are required for context state persistence")

        payload = dict(state or {})
        client = self.redis_client
        if client is not None:
            try:
                client.set(self._key(agent_id, context_id), json.dumps(payload, default=str), ex=self.ttl_seconds)
                return
            except Exception:
                pass

        with self._memory_lock:
            self._memory_store[self._key(agent_id, context_id)] = payload
