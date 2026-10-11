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

"""PrometheusWorker — base class for blocking workloads run on a worker thread.

Run synchronous, blocking code (a legacy library, a synchronous SDK, a CPU loop)
without freezing the agent's single event loop. The worker's :meth:`run` executes
off-loop via :meth:`PrometheusAgent.run_worker`; from inside ``run`` it cannot
touch the loop-bound A2A event queue (an ``asyncio.Queue`` is not thread-safe), so
it emits a **safe subset** of events into a thread-safe mailbox that the event loop
drains and forwards.

Only pure, no-I/O event construction is available, mirroring a subset of the
``PrometheusAgent.send_*`` helpers:

- :meth:`emit_status_update`  ~ ``PrometheusAgent.send_status_update``
- :meth:`emit_json_artifact`  ~ ``PrometheusAgent.send_json_artifact`` (inline only)

Operations that require ``await``-ing loop-bound I/O are intentionally **not**
available here — DeepLynx uploads, artifact-catalog registration, durable
conversation messages, ``INPUT_REQUIRED``. Do those from ``_execute`` on the loop,
before or after ``run_worker``.

Example::

    class CrunchWorker(PrometheusWorker):
        def run(self):
            total = len(self.items)
            for i, item in enumerate(self.items, 1):
                if self.cancelled:
                    return {"status": "cancelled", "done": i - 1}
                self.emit_status_update(f"Crunching {i}/{total}…")
                heavy_blocking_call(item)
            return {"status": "success", "processed": total}

    # inside PrometheusAgent._execute:
    worker = CrunchWorker(); worker.items = params["items"]
    result = await self.run_worker(worker, context, event_queue)
"""

import queue
import threading
from typing import Any, Dict, List, Optional

from a2a.server.agent_execution.context import RequestContext
from a2a.types import TaskState

from .events import build_data_artifact_event, build_status_update_event


class PrometheusWorker:
    """Base class for a synchronous, blocking workload run on a worker thread.

    Subclass and override :meth:`run`. Inside ``run`` (which executes on a worker
    thread), call the ``emit_*`` methods to stream progress and check
    :attr:`cancelled` periodically to stop early. Run it from an agent with
    ``await self.run_worker(worker, context, event_queue)``.
    """

    DEFAULT_MAILBOX_SIZE = 256

    def __init__(self, *, mailbox_size: int = DEFAULT_MAILBOX_SIZE) -> None:
        # Thread-safe mailbox of fully-built A2A events. Bounded so a fast worker
        # applies backpressure (its put() blocks) instead of growing unbounded.
        self._mailbox: "queue.Queue[Any]" = queue.Queue(maxsize=mailbox_size)
        self._cancel = threading.Event()
        self._context: Optional[RequestContext] = None
        self._agent_name: str = "Agent"

    # ------------------------------------------------------------------ #
    # Wiring + draining — used by PrometheusAgent.run_worker (on the loop)
    # ------------------------------------------------------------------ #
    def _bind(self, context: RequestContext, agent_name: str) -> None:
        """Give the worker the context/agent identity needed to build events."""
        self._context = context
        self._agent_name = agent_name

    def _require_context(self) -> RequestContext:
        if self._context is None:
            raise RuntimeError(
                "PrometheusWorker is not bound to a request; run it via "
                "PrometheusAgent.run_worker()."
            )
        return self._context

    def drain(self) -> List[Any]:
        """Pop all queued events (called from the event loop)."""
        events: List[Any] = []
        while True:
            try:
                events.append(self._mailbox.get_nowait())
            except queue.Empty:
                return events

    # ------------------------------------------------------------------ #
    # Cooperative cancellation
    # ------------------------------------------------------------------ #
    def cancel(self) -> None:
        """Request cancellation (set by run_worker when the caller goes away)."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        """True once cancellation was requested; ``run`` should check this and
        stop promptly (Python threads cannot be force-killed)."""
        return self._cancel.is_set()

    # ------------------------------------------------------------------ #
    # Emit API — called FROM the worker thread inside run().
    # Mirrors a safe subset of PrometheusAgent.send_* (pure construction only).
    # ------------------------------------------------------------------ #
    def emit_status_update(
        self,
        message: Optional[str] = None,
        *,
        state: TaskState = TaskState.TASK_STATE_WORKING,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Queue a progress status update. Mirror of
        ``PrometheusAgent.send_status_update`` (always non-final — the base
        executor finalizes the task from ``run``'s return value)."""
        event = build_status_update_event(
            context=self._require_context(),
            state=state,
            final=False,
            message=message,
            metadata=metadata,
        )
        self._mailbox.put(event)  # blocks if the mailbox is full → backpressure

    def emit_json_artifact(
        self,
        payload: Any,
        *,
        name: str = "result",
        description: Optional[str] = None,
        json_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
        append: bool = False,
        last_chunk: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Queue an inline JSON artifact. Mirror of
        ``PrometheusAgent.send_json_artifact`` for inline artifacts only.

        Not cataloged — catalog registration is loop-bound I/O and is excluded
        from the worker's safe subset. Ideal for streaming verbose output from a
        long simulation, optionally in chunks via ``append`` / ``last_chunk``.
        Returns the ``artifact_id`` (reuse it for subsequent chunks).
        """
        event, artifact_id = build_data_artifact_event(
            context=self._require_context(),
            agent_name=self._agent_name,
            payload=payload,
            name=name,
            description=description,
            json_type=json_type,
            artifact_id=artifact_id,
            append=append,
            last_chunk=last_chunk,
            metadata=metadata,
        )
        self._mailbox.put(event)
        return artifact_id

    # ------------------------------------------------------------------ #
    # The workload — override this
    # ------------------------------------------------------------------ #
    def run(self) -> Dict[str, Any]:
        """Override with synchronous, blocking work. Runs on a worker thread.

        Call ``self.emit_status_update(...)`` / ``self.emit_json_artifact(...)``
        to stream progress, and check ``self.cancelled`` periodically to stop
        early. The returned dict becomes the agent's final result.
        """
        raise NotImplementedError("Subclasses must implement run() with their blocking workload.")
