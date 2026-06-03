"""
Thread Pattern Debug Agent
==========================

A reference agent for running **long, blocking work** without freezing the
single event loop, using ``PrometheusWorker`` + ``PrometheusAgent.run_worker``.

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
Put the blocking work in a ``PrometheusWorker.run()`` (plain synchronous code on
a worker thread). From inside ``run`` it emits progress with the safe-subset
helpers — ``emit_status_update`` and ``emit_json_artifact`` — into a thread-safe
mailbox. ``await self.run_worker(worker, context, event_queue)`` runs it off-loop
and drains that mailbox from the event loop, so the loop stays free for the
heartbeat and SSE to keep flowing. The worker checks ``self.cancelled`` to stop
cooperatively (threads cannot be force-killed).

Skills
------
- ``run_blocking_task``    — foreground demo. The client-agent waits for it;
  status (and a JSON summary artifact) stream the whole time. Optional
  ``duration_seconds`` (default 60) controls how long the worker blocks.
- ``run_background_task``  — SCAFFOLDED ONLY. Shows where a future "detach and
  return immediately" background-task implementation would go. Not implemented;
  the intended A2A task flow is written out as comments.
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict

from prometheus_api.agent import PrometheusAgent, PrometheusWorker
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue

# Skill identifiers (must match agent_card.json).
SKILL_BLOCKING = "run_blocking_task"
SKILL_BACKGROUND = "run_background_task"

DEFAULT_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 600
# How often run_worker drains progress and lets the loop breathe. Keep this well
# under the heartbeat interval (default 15s) so real progress updates supersede
# heartbeats while the worker is reporting.
POLL_INTERVAL_SECONDS = 1.0


class BlockingDemoWorker(PrometheusWorker):
    """Stand-in for a real blocking workload (a sync SDK, a legacy analysis tool,
    a CPU loop). It blocks in one-second steps so it can report progress and
    honour cooperative cancellation. A truly opaque blocking call (a single
    ``library.run()`` with no hooks) could not report mid-flight — there the
    loop-side heartbeat alone keeps the connection alive.
    """

    def __init__(self, duration_seconds: int) -> None:
        super().__init__()
        self.duration_seconds = duration_seconds

    def run(self) -> Dict[str, Any]:
        start = time.monotonic()
        elapsed = 0
        while elapsed < self.duration_seconds:
            if self.cancelled:
                return {
                    "status": "cancelled",
                    "requested_seconds": self.duration_seconds,
                    "elapsed_seconds": elapsed,
                }
            time.sleep(1)  # the blocking wait that never yields to the event loop
            elapsed = int(time.monotonic() - start)
            self.emit_status_update(
                f"Blocking compute in progress… {elapsed}/{self.duration_seconds}s elapsed."
            )

        # A JSON artifact is handy for verbose, structured progress output —
        # e.g. intermediate results streamed from a long numerical simulation.
        self.emit_json_artifact(
            {"requested_seconds": self.duration_seconds, "elapsed_seconds": elapsed},
            name="blocking_task_summary",
            json_type="prometheus.debug.blocking_summary.v1",
        )
        return {
            "status": "success",
            "requested_seconds": self.duration_seconds,
            "elapsed_seconds": elapsed,
        }


class ThreadPatternAgent(PrometheusAgent):
    """Reference agent for the offload-and-observe pattern."""

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
    # Skill 1: foreground blocking task (PrometheusWorker + run_worker)
    # ------------------------------------------------------------------ #
    async def _run_foreground_blocking(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
        duration_seconds: int,
    ) -> Dict[str, Any]:
        """Run a blocking compute on a worker thread, streaming progress.

        The client-agent waits for this skill; because the blocking work runs
        off-loop and run_worker forwards the worker's events from the loop, the
        caller sees a steady stream of status updates (plus heartbeats) for the
        whole duration instead of a silent connection that times out.
        """
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Starting blocking task ({duration_seconds}s) on a worker thread…",
        )

        worker = BlockingDemoWorker(duration_seconds)
        # run_worker runs worker.run() off-loop, forwards its emitted events from
        # the loop, flushes on completion, re-raises worker errors, and on caller
        # cancellation signals the worker to stop cooperatively.
        result = await self.run_worker(
            worker, context, event_queue, poll_interval=POLL_INTERVAL_SECONDS
        )
        result.setdefault("message", f"Blocking task finished after {result.get('elapsed_seconds')}s.")
        return result

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
        #   # 2) Hand the work to the job runner (survives this request). The job
        #   #    runs a PrometheusWorker exactly like the foreground path, but its
        #   #    events are delivered to a detached, durable consumer:
        #   await job_runner.enqueue(
        #       agent="thread-pattern-agent", skill=SKILL_BACKGROUND,
        #       task_id=task_id, params={"duration_seconds": duration_seconds},
        #   )
        #
        #   # 3) The worker finishes, writes its result to the durable task store,
        #   #    and a FINAL completed status is emitted for task_id
        #   #    (state=TaskState.completed, final=True). Delivery to the frontend
        #   #    happens via push notification or the next tasks/get / resubscribe.
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
