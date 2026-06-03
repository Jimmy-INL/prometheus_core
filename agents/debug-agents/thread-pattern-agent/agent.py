"""
Thread Pattern Debug Agent
==========================

A reference agent that demonstrates the canonical pattern for running
**long, blocking work** inside an ``async def _execute`` without freezing the
single event loop — and for surfacing progress from that work.

Why this matters
----------------
A Prometheus agent runs as one process with one asyncio event loop. A blocking
call (a synchronous SDK, a legacy library, a CPU loop, ``time.sleep``) does not
``await``, so while it runs nothing else on the loop can run: not the keepalive
heartbeat, not the A2A SSE consumer that flushes bytes to the caller, not other
clients. If the gap exceeds the upstream socket-read timeout (LiteLLM/aiohttp),
the streaming connection is torn down even though the agent is still working.

The pattern
-----------
1. Run the blocking work in a worker thread via ``asyncio.to_thread`` so the
   loop stays free.
2. The worker thread must NOT touch ``event_queue`` — it wraps a loop-bound
   ``asyncio.Queue`` that is not thread-safe. Instead the thread writes progress
   into a thread-safe :class:`ProgressReporter` (a ``queue.Queue``).
3. The ``_execute`` coroutine *observes* the thread: it polls the reporter,
   emits ``send_status_update`` calls itself (on the loop, where that is safe),
   and ``await asyncio.sleep(...)`` between polls. That sleep is what keeps the
   loop breathing, so the heartbeat fires and the SSE stream keeps flushing.
4. ``await`` the worker task at the end to recover the result and re-raise any
   exception, so the base executor's failure handling still applies.

Skills
------
- ``run_blocking_task``    — foreground demo of the thread/observe pattern. The
  client-agent waits for it; progress streams the whole time. Optional
  ``duration_seconds`` (default 60) controls how long the worker blocks.
- ``run_background_task``  — SCAFFOLDED ONLY. Shows where a future "detach and
  return immediately" background-task implementation would go. Not implemented;
  the intended A2A task flow is written out as comments.
"""
import asyncio
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from prometheus_api.agent import PrometheusAgent
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue

# Skill identifiers (must match agent_card.json).
SKILL_BLOCKING = "run_blocking_task"
SKILL_BACKGROUND = "run_background_task"

DEFAULT_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 600
# How often the observer coroutine wakes to drain progress and let the loop
# breathe. Keep this well under the heartbeat interval (default 15s) so real
# progress updates supersede heartbeats while the worker is reporting.
POLL_INTERVAL_SECONDS = 1.0


class ProgressReporter:
    """Thread-safe, one-way progress channel.

    The worker THREAD calls :meth:`report`; the event LOOP calls :meth:`drain`.
    Backed by ``queue.Queue`` so that every message survives even when the
    worker reports several times between two drains — a plain "latest value"
    field would drop the intermediate updates. The worker never touches the
    loop-bound asyncio ``EventQueue`` (which is not thread-safe).
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[str]" = queue.Queue()

    def report(self, message: str) -> None:
        """Called from the worker thread."""
        self._queue.put(str(message))

    def drain(self) -> List[str]:
        """Called from the event loop. Returns all messages queued so far."""
        messages: List[str] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages


class ThreadPatternAgent(PrometheusAgent):
    """Reference agent for the offload-and-observe pattern."""

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        # The base executor injects the invoked skill as params["skill_id"]
        # from the A2A message metadata. Default to the foreground demo.
        skill_id = str(params.get("skill_id") or SKILL_BLOCKING)
        duration_seconds = self._resolve_duration_seconds(params)

        if skill_id == SKILL_BACKGROUND:
            return await self._run_background_task(params, context, event_queue, duration_seconds)
        return await self._run_foreground_blocking(params, context, event_queue, duration_seconds)

    @staticmethod
    def _resolve_duration_seconds(params: Dict[str, Any]) -> int:
        """Read the optional duration parameter, clamped to a sane range."""
        raw = params.get("duration_seconds", DEFAULT_DURATION_SECONDS)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_DURATION_SECONDS
        return max(1, min(value, MAX_DURATION_SECONDS))

    # ------------------------------------------------------------------ #
    # Skill 1: foreground blocking task (thread + observe pattern)
    # ------------------------------------------------------------------ #
    async def _run_foreground_blocking(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
        duration_seconds: int,
    ) -> Dict[str, Any]:
        """Run a blocking compute on a worker thread, streaming progress.

        The client-agent waits for this skill; because we offload the blocking
        work and emit progress from the loop, the caller sees a steady stream of
        status updates (plus heartbeats) for the whole duration instead of a
        silent connection that times out.
        """
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Starting blocking task ({duration_seconds}s) on a worker thread…",
        )

        progress = ProgressReporter()
        # Cooperative cancellation: threads cannot be force-killed in Python, so
        # the worker checks this flag and stops on its own when asked.
        cancel_event = threading.Event()

        # Launch the blocking work off the event loop.
        work = asyncio.create_task(
            asyncio.to_thread(self._blocking_compute, duration_seconds, progress, cancel_event)
        )

        try:
            # Observe the thread from the loop: drain progress, emit on the loop,
            # and sleep (which yields → heartbeat + SSE keep flowing).
            while not work.done():
                for message in progress.drain():
                    await self.send_status_update(
                        context=context, event_queue=event_queue, message=message
                    )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

            # Flush any progress reported between the last poll and completion.
            for message in progress.drain():
                await self.send_status_update(
                    context=context, event_queue=event_queue, message=message
                )

            # Recover the result and re-raise any exception from the thread.
            result = await work
        except asyncio.CancelledError:
            # Caller went away (disconnect / cancel). Ask the worker to stop so
            # we do not leave an orphaned thread burning a worker slot.
            cancel_event.set()
            raise

        result.setdefault("message", f"Blocking task finished after {result.get('elapsed_seconds')}s.")
        return result

    @staticmethod
    def _blocking_compute(
        duration_seconds: int,
        progress: ProgressReporter,
        cancel_event: threading.Event,
    ) -> Dict[str, Any]:
        """Pure synchronous work — runs in a worker thread, no asyncio here.

        Stands in for a real blocking call (a sync SDK, legacy analysis tool, or
        CPU loop). It blocks in one-second steps so it can report progress and
        honour cooperative cancellation. A truly opaque blocking call (a single
        ``library.run()`` with no hooks) could not report mid-flight — in that
        case the loop-side heartbeat alone keeps the connection alive.
        """
        start = time.monotonic()
        elapsed = 0
        while elapsed < duration_seconds:
            if cancel_event.is_set():
                return {
                    "status": "cancelled",
                    "requested_seconds": duration_seconds,
                    "elapsed_seconds": elapsed,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            time.sleep(1)  # the blocking wait that never yields to the event loop
            elapsed = int(time.monotonic() - start)
            progress.report(f"Blocking compute in progress… {elapsed}/{duration_seconds}s elapsed.")

        return {
            "status": "success",
            "requested_seconds": duration_seconds,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    # Skill 2: background task (SCAFFOLDED — NOT YET IMPLEMENTED)
    # ------------------------------------------------------------------ #
    async def _run_background_task(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
        duration_seconds: int,
    ) -> Dict[str, Any]:
        """Placeholder for a detached background-task implementation.

        Intended behaviour, once background tasks are supported platform-wide:
        return immediately with an A2A ``working`` status (freeing the frontend
        to keep prompting), run the blocking work detached from this request,
        and deliver the final result out-of-band when the worker finishes.

        The mechanics are intentionally left as comments until the background
        task feature lands; see the design notes below.
        """
        # ---- INTENDED BACKGROUND-TASK FLOW (not yet implemented) ----------
        #
        # Prerequisites the platform still needs before this can work:
        #   * A durable task store (Redis-backed) replacing the in-memory one,
        #     so the task survives this request and an agent restart, and the
        #     frontend can reattach to it later.
        #   * A delivery channel: A2A push notifications (the `pushNotifications`
        #     capability, currently false) and/or client polling via `tasks/get`
        #     / re-subscription via `tasks/resubscribe`.
        #   * Detached execution that outlives the request — ideally a real job
        #     runner (Redis queue + worker), NOT an OS thread held for the whole
        #     job (a thread per long task would exhaust the worker pool).
        #
        # Sketch of the handler once those exist:
        #
        #   task_id = context.task_id
        #
        #   # 1) Emit a non-final "working" status and return right away so the
        #   #    caller is freed. (final=False keeps the task open.)
        #   await emit_status_update(
        #       context=context, event_queue=event_queue,
        #       state=TaskState.working, final=False,
        #       message=f"Accepted; running ~{duration_seconds}s in the background.",
        #   )
        #
        #   # 2) Hand the work to the job runner (survives this request):
        #   await job_runner.enqueue(
        #       agent="thread-pattern-agent", skill=SKILL_BACKGROUND,
        #       task_id=task_id, params={"duration_seconds": duration_seconds},
        #   )
        #
        #   # 3) The worker runs _blocking_compute(), then writes the result to
        #   #    the durable task store and emits a FINAL completed status for
        #   #    task_id (state=TaskState.completed, final=True). Delivery to the
        #   #    frontend happens via push notification or on the next
        #   #    tasks/get / tasks/resubscribe.
        #
        #   # 4) Return the working acknowledgement to the caller now.
        #   return {"status": "working", "task_id": task_id, "background": True}
        # -------------------------------------------------------------------

        return {
            "status": "not_implemented",
            "skill_id": SKILL_BACKGROUND,
            "message": (
                "Background execution is scaffolded but not yet implemented. "
                "Use 'run_blocking_task' for the foreground thread/observe demo. "
                "See the comments in _run_background_task for the intended A2A flow."
            ),
            "requested_seconds": duration_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    agent = ThreadPatternAgent(agent_name="Thread Pattern Debug Agent")
    agent.run()
