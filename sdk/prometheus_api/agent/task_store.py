"""Redis-backed A2A ``TaskStore``.

The A2A SDK ships an ``InMemoryTaskStore`` whose contents vanish when the agent
process stops. For background / long-running tasks that must outlive the request
that started them (and survive an agent restart), task state has to be durable.

``RedisTaskStore`` implements the A2A ``TaskStore`` interface (``save`` / ``get`` /
``delete``) against Redis, mirroring the connection + graceful-fallback pattern
used by :class:`ArtifactRegistry`: if Redis is unreachable it degrades to a
process-local dict so a single agent keeps working (just without cross-process
durability).

Redis calls are offloaded with :func:`asyncio.to_thread` so the synchronous
``redis-py`` client never blocks the event loop the A2A request handler runs on.

See ``prometheus_platform/docs/dev-docs/background-tasks.md`` (Layer A).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, Optional

from ..redis_utils import create_redis_client

from a2a.server.tasks import TaskStore
from a2a.types import Task, TaskState

logger = logging.getLogger(__name__)

#: States a task can rest in; these never change again.
TERMINAL_STATES = frozenset(
    {
        TaskState.completed,
        TaskState.canceled,
        TaskState.failed,
        TaskState.rejected,
    }
)


class RedisTaskStore(TaskStore):
    """Durable A2A task store backed by Redis with an in-memory fallback."""

    DEFAULT_TTL_SECONDS = 24 * 3600

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_password = os.getenv("REDIS_PASSWORD")

        configured_ttl = os.getenv("TASK_STORE_TTL_SECONDS", "").strip()
        ttl = ttl_seconds
        if ttl is None and configured_ttl:
            try:
                ttl = int(configured_ttl)
            except ValueError:
                ttl = None
        self.ttl_seconds = ttl if ttl is not None else self.DEFAULT_TTL_SECONDS

        self._redis = None
        self._memory_lock = threading.Lock()
        self._memory_store: Dict[str, str] = {}

    # --- keys ---------------------------------------------------------------

    @staticmethod
    def _key(task_id: str) -> str:
        return f"a2a:task:{task_id}"

    # --- connection (mirrors ArtifactRegistry.redis_client) -----------------

    @property
    def redis_client(self):
        if self._redis is None:
            self._redis = create_redis_client(self.redis_url, password=self.redis_password)
        return self._redis

    # --- TaskStore interface ------------------------------------------------

    async def save(self, task: Task, context: Any | None = None) -> None:
        data = task.model_dump_json()
        await asyncio.to_thread(self._save_sync, task.id, data)

    async def get(self, task_id: str, context: Any | None = None) -> Optional[Task]:
        data = await asyncio.to_thread(self._get_sync, task_id)
        if not data:
            return None
        try:
            return Task.model_validate_json(data)
        except Exception as exc:
            logger.warning("[TASKSTORE] Corrupt task payload for %s: %s", task_id, exc)
            return None

    async def delete(self, task_id: str, context: Any | None = None) -> None:
        await asyncio.to_thread(self._delete_sync, task_id)

    # --- sync workers (run off the event loop via to_thread) ----------------

    def _save_sync(self, task_id: str, data: str) -> None:
        client = self.redis_client
        if client is not None:
            try:
                key = self._key(task_id)
                if self.ttl_seconds > 0:
                    client.set(key, data, ex=self.ttl_seconds)
                else:
                    client.set(key, data)
                return
            except Exception as exc:
                logger.warning("[TASKSTORE] Redis save failed for %s: %s", task_id, exc)
        with self._memory_lock:
            self._memory_store[task_id] = data

    def _get_sync(self, task_id: str) -> Optional[str]:
        client = self.redis_client
        if client is not None:
            try:
                val = client.get(self._key(task_id))
                if val is not None:
                    return str(val)
            except Exception as exc:
                logger.warning("[TASKSTORE] Redis get failed for %s: %s", task_id, exc)
        with self._memory_lock:
            return self._memory_store.get(task_id)

    def _delete_sync(self, task_id: str) -> None:
        client = self.redis_client
        if client is not None:
            try:
                client.delete(self._key(task_id))
            except Exception as exc:
                logger.warning("[TASKSTORE] Redis delete failed for %s: %s", task_id, exc)
        with self._memory_lock:
            self._memory_store.pop(task_id, None)
