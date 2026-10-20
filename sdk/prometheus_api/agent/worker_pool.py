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

"""Per-user worker process pool for credential-touching agents.

When a :class:`PrometheusAgent` subclass sets ``requires_user_isolation = True``,
every incoming request is routed to a *dedicated OS process* for the calling
user.  This bounds secret exposure: a per-user process holds at most one user's
JIT-fetched credentials in its memory space.  A scoping bug, memory leak, or
crash in one user's process cannot expose another user's secrets.

Architecture
------------
- ``UserWorkerPool`` maintains one ``WorkerHandle`` per ``user_id`` (a process +
  two multiprocessing queues for request/response).
- The supervisor (parent) process marshals ``WorkerTask`` to the worker and
  receives ``WorkerResult`` back, routing events to the parent ``EventQueue``.
- Workers are spawned lazily on first request and reaped after
  ``USER_WORKER_IDLE_TTL`` seconds of inactivity.
- A hard cap ``USER_WORKER_MAX`` prevents unbounded process growth.

Request isolation guarantees
-----------------------------
- The worker enters an :func:`~prometheus_api.agent.identity.identity_scope`
  before calling ``_execute``, so ``current_user_id()`` returns the correct
  value inside the subprocess.
- The parent never passes the user's raw token to other workers; each worker
  process holds exactly the token(s) associated with *its* user_id.
- Worker processes do not inherit the parent's in-process credential caches
  because ``multiprocessing.Process`` (``spawn`` start method) does not fork
  the parent's memory space.

Integration with PrometheusAgentExecutor
-----------------------------------------
When ``PrometheusAgent.requires_user_isolation = True``, the ``_execute``
method override in the subclass calls
``UserWorkerPool.run_in_worker(user_id, raw_token, params, execute_fn, context, event_queue)``
instead of running ``_execute`` directly.  See the docstring for
:meth:`UserWorkerPool.run_in_worker` for the expected ``execute_fn`` signature.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
from multiprocessing.process import BaseProcess
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (from env)
# ---------------------------------------------------------------------------


def _idle_ttl() -> float:
    raw = os.getenv("USER_WORKER_IDLE_TTL", "300").strip()
    try:
        return max(float(raw), 10.0)
    except ValueError:
        return 300.0


def _max_workers() -> int:
    raw = os.getenv("USER_WORKER_MAX", "32").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 32


# ---------------------------------------------------------------------------
# Intra-process communication types
# ---------------------------------------------------------------------------


@dataclass
class WorkerTask:
    """Payload sent from supervisor to worker."""

    task_id: str
    user_id: str
    raw_token: str
    params: Dict[str, Any]
    context_data: Dict[str, Any]  # serialised subset of RequestContext

    def __repr__(self) -> str:
        # Never include raw_token in repr (would appear in logs).
        return (
            f"WorkerTask(task_id={self.task_id!r}, user_id={self.user_id!r}, "
            f"params_keys={sorted(self.params.keys())})"
        )


@dataclass
class WorkerResult:
    """Payload sent from worker to supervisor."""

    task_id: str
    user_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Worker subprocess entry point
# ---------------------------------------------------------------------------


def _worker_loop(
    user_id: str,
    request_queue: multiprocessing.Queue,
    response_queue: multiprocessing.Queue,
    idle_ttl: float,
    execute_fn_module: str,
    execute_fn_name: str,
) -> None:
    """Main loop for a per-user worker process.

    Pulled tasks from *request_queue*, executes them inside an identity scope,
    and returns results on *response_queue*.  Exits after *idle_ttl* seconds of
    inactivity.
    """
    import asyncio
    import importlib

    try:
        module = importlib.import_module(execute_fn_module)
        execute_fn = getattr(module, execute_fn_name)
    except Exception as exc:
        # Fatal: can't load the execute function.  Notify supervisor and exit.
        response_queue.put(
            WorkerResult(task_id="__init__", user_id=user_id, error=f"Worker init failed: {exc}")
        )
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def run(task: WorkerTask) -> WorkerResult:
        from prometheus_api.agent.identity import (
            identity_scope,
            verify_user_token,
        )

        events: List[Dict[str, Any]] = []

        try:
            # Verify the token (defence-in-depth; parent verified it already).
            identity = verify_user_token(task.raw_token)
        except Exception as exc:
            return WorkerResult(task_id=task.task_id, user_id=user_id, error=str(exc))

        async def _run_with_scope() -> Dict[str, Any]:
            with identity_scope(identity):
                task_result: Dict[str, Any] = await execute_fn(task.params, task.context_data)
                return task_result

        try:
            result = loop.run_until_complete(_run_with_scope())
            return WorkerResult(
                task_id=task.task_id,
                user_id=user_id,
                result=result,
                events=events,
            )
        except Exception as exc:
            return WorkerResult(task_id=task.task_id, user_id=user_id, error=str(exc))

    last_active = time.monotonic()
    while True:
        # Poll for new tasks, checking idle timeout.
        try:
            task: WorkerTask = request_queue.get(timeout=1.0)
            last_active = time.monotonic()
            result = run(task)
            response_queue.put(result)
        except Exception:
            # Empty queue (get() raises Empty on timeout) or other transient error.
            if time.monotonic() - last_active > idle_ttl:
                logger.debug("Worker for %r exiting after %.0fs idle", user_id, idle_ttl)
                break


# ---------------------------------------------------------------------------
# WorkerHandle — one per active user
# ---------------------------------------------------------------------------


class WorkerHandle:
    """Represents a live per-user subprocess."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.request_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.response_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.process: Optional[BaseProcess] = None
        self.last_used: float = time.monotonic()
        self._pending: Dict[str, asyncio.Future] = {}

    def is_alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def terminate(self) -> None:
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=3.0)


# ---------------------------------------------------------------------------
# UserWorkerPool — supervisor
# ---------------------------------------------------------------------------


class UserWorkerPool:
    """Supervisor that manages one subprocess per active user.

    Thread/task safety: all public methods must be called from the same asyncio
    event loop.  Internal state is protected by an asyncio.Lock.

    Environment variables:
        ``USER_WORKER_IDLE_TTL`` — seconds of inactivity before a worker exits
            (default: 300).
        ``USER_WORKER_MAX`` — maximum concurrent worker processes (default: 32).
    """

    def __init__(
        self,
        execute_fn_module: str,
        execute_fn_name: str,
    ) -> None:
        """
        Args:
            execute_fn_module: Importable module path for the execute function,
                e.g. ``"myagent.agent"``.
            execute_fn_name: Name of the async coroutine in that module, e.g.
                ``"isolated_execute"``.
        """
        self._workers: Dict[str, WorkerHandle] = {}
        self._lock = asyncio.Lock()
        self._execute_fn_module = execute_fn_module
        self._execute_fn_name = execute_fn_name
        self._idle_ttl = _idle_ttl()
        self._max_workers = _max_workers()
        self._reaper_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the idle-worker reaper background task."""
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop(self) -> None:
        """Terminate all workers and cancel the reaper."""
        if self._reaper_task:
            self._reaper_task.cancel()
        async with self._lock:
            for handle in list(self._workers.values()):
                handle.terminate()
            self._workers.clear()

    async def run_in_worker(
        self,
        user_id: str,
        raw_token: str,
        task_id: str,
        params: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route *params* to the per-user worker and return the result.

        A new worker is spawned if one does not already exist for *user_id*.

        Args:
            user_id: The authenticated user identifier.
            raw_token: The user's raw platform JWT (forwarded to the worker
                for re-verification inside the identity scope).
            task_id: A unique ID for this specific task (for tracing).
            params: The ``params`` dict from the agent executor.
            context_data: A serialisable subset of the A2A ``RequestContext``
                (e.g. ``{"context_id": ..., "task_id": ...}``).

        Returns:
            The ``result`` dict produced by the worker's execute function.

        Raises:
            RuntimeError: If the worker pool is at capacity.
            Exception: Worker-side errors are re-raised in the caller's context.
        """
        handle = await self._get_or_spawn(user_id)
        task = WorkerTask(
            task_id=task_id,
            user_id=user_id,
            raw_token=raw_token,
            params=params,
            context_data=context_data,
        )
        loop = asyncio.get_running_loop()
        handle.request_queue.put(task)

        # Poll the response queue asynchronously without blocking the event loop.
        while True:
            try:
                worker_result: WorkerResult = await loop.run_in_executor(
                    None, lambda: handle.response_queue.get(timeout=0.5)
                )
            except Exception:
                # Timeout or transient error — check if the process died.
                if not handle.is_alive():
                    async with self._lock:
                        self._workers.pop(user_id, None)
                    raise RuntimeError(f"Worker process for user {user_id!r} died unexpectedly")
                continue

            handle.last_used = time.monotonic()
            if worker_result.task_id != task_id:
                # Stale result from a previous task (shouldn't happen, but guard).
                continue
            if worker_result.error:
                raise RuntimeError(f"Worker error for {user_id!r}: {worker_result.error}")
            return worker_result.result or {}

    async def _get_or_spawn(self, user_id: str) -> WorkerHandle:
        """Return an existing live worker or spawn a new one."""
        async with self._lock:
            handle = self._workers.get(user_id)
            if handle and handle.is_alive():
                return handle
            # Reap dead handle if present.
            if handle:
                del self._workers[user_id]

            if len(self._workers) >= self._max_workers:
                raise RuntimeError(
                    f"UserWorkerPool at capacity ({self._max_workers} workers); "
                    f"cannot spawn worker for {user_id!r}"
                )

            handle = WorkerHandle(user_id=user_id)
            ctx = multiprocessing.get_context("spawn")
            proc = ctx.Process(
                target=_worker_loop,
                args=(
                    user_id,
                    handle.request_queue,
                    handle.response_queue,
                    self._idle_ttl,
                    self._execute_fn_module,
                    self._execute_fn_name,
                ),
                daemon=True,
                name=f"prometheus-user-worker-{user_id}",
            )
            proc.start()
            handle.process = proc
            self._workers[user_id] = handle
            logger.info("Spawned worker PID %d for user %r", proc.pid or -1, user_id)
            return handle

    async def _reaper_loop(self) -> None:
        """Periodically remove dead or idle workers from the pool."""
        while True:
            await asyncio.sleep(30.0)
            async with self._lock:
                now = time.monotonic()
                to_remove = [
                    uid
                    for uid, h in self._workers.items()
                    if not h.is_alive() or (now - h.last_used) > self._idle_ttl
                ]
                for uid in to_remove:
                    h = self._workers.pop(uid)
                    h.terminate()
                    logger.debug("Reaped worker for %r", uid)
