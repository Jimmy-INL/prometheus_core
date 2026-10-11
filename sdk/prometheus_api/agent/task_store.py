# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

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

See ``platform/docs/dev-docs/background-tasks.md`` (Layer A).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, List, Optional, cast

from ..redis_utils import create_redis_client

from a2a.server.tasks import TaskStore
from a2a.types import ListTasksRequest, ListTasksResponse, Task, TaskState
from a2a.utils.constants import DEFAULT_LIST_TASKS_PAGE_SIZE
from a2a.utils.errors import InvalidParamsError
from a2a.utils.task import decode_page_token, encode_page_token
from google.protobuf.json_format import MessageToJson, Parse

logger = logging.getLogger(__name__)

#: States a task can rest in; these never change again.
TERMINAL_STATES = frozenset(
    {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_REJECTED,
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
        data = MessageToJson(task)
        await asyncio.to_thread(self._save_sync, task.id, data)

    async def get(self, task_id: str, context: Any | None = None) -> Optional[Task]:
        data = await asyncio.to_thread(self._get_sync, task_id)
        if not data:
            return None
        try:
            return cast(Task, Parse(data, Task()))
        except Exception as exc:
            logger.warning("[TASKSTORE] Corrupt task payload for %s: %s", task_id, exc)
            return None

    async def delete(self, task_id: str, context: Any | None = None) -> None:
        await asyncio.to_thread(self._delete_sync, task_id)

    # The A2A v1 TaskStore ABC requires this exact name despite shadowing list.
    async def list(
        self,
        params: ListTasksRequest,
        context: Any | None = None,
    ) -> ListTasksResponse:
        """List persisted tasks using the filtering and pagination required by v1."""
        tasks = await asyncio.to_thread(self._list_sync)
        if params.context_id:
            tasks = [task for task in tasks if task.context_id == params.context_id]
        if params.status:
            tasks = [task for task in tasks if task.status.state == params.status]
        if params.HasField("status_timestamp_after"):
            cutoff = params.status_timestamp_after.ToJsonString()
            tasks = [
                task
                for task in tasks
                if task.HasField("status")
                and task.status.HasField("timestamp")
                and task.status.timestamp.ToJsonString() >= cutoff
            ]

        tasks.sort(
            key=lambda task: (
                task.status.timestamp.ToJsonString()
                if task.HasField("status") and task.status.HasField("timestamp")
                else "",
                task.id,
            ),
            reverse=True,
        )
        total_size = len(tasks)
        start_idx = 0
        if params.page_token:
            start_task_id = decode_page_token(params.page_token)
            for index, task in enumerate(tasks):
                if task.id == start_task_id:
                    start_idx = index
                    break
            else:
                raise InvalidParamsError(f"Invalid page token: {params.page_token}")

        page_size = params.page_size or DEFAULT_LIST_TASKS_PAGE_SIZE
        end_idx = start_idx + page_size
        next_page_token = encode_page_token(tasks[end_idx].id) if end_idx < total_size else None
        return ListTasksResponse(
            tasks=tasks[start_idx:end_idx],
            next_page_token=next_page_token,
            page_size=page_size,
            total_size=total_size,
        )

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

    def _list_sync(self) -> List[Task]:
        serialized_by_id: Dict[str, str] = {}
        client = self.redis_client
        if client is not None:
            try:
                for key in client.scan_iter(match="a2a:task:*"):
                    data = client.get(key)
                    if data:
                        serialized_by_id[str(key).removeprefix("a2a:task:")] = str(data)
            except Exception as exc:
                logger.warning("[TASKSTORE] Redis list failed: %s", exc)
        with self._memory_lock:
            serialized_by_id.update(self._memory_store)

        tasks: List[Task] = []
        for task_id, data in serialized_by_id.items():
            try:
                tasks.append(cast(Task, Parse(data, Task())))
            except Exception as exc:
                logger.warning("[TASKSTORE] Corrupt task payload for %s: %s", task_id, exc)
        return tasks

    def _delete_sync(self, task_id: str) -> None:
        client = self.redis_client
        if client is not None:
            try:
                client.delete(self._key(task_id))
            except Exception as exc:
                logger.warning("[TASKSTORE] Redis delete failed for %s: %s", task_id, exc)
        with self._memory_lock:
            self._memory_store.pop(task_id, None)
