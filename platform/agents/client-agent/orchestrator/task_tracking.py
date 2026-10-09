"""Turn- and skill-level integration with the Task Graph.

This is the thin layer that turns orchestrator activity into Task Graph nodes:

- ``begin_turn`` / ``finish_turn`` bracket one user turn. The *root* node is
  created lazily — only if the turn actually dispatches a skill — so plain
  conversational answers and follow-up prompts don't litter the graph.
- ``track_skill`` is an async context manager wrapped around each skill
  dispatch. It creates a child node under the current parent, marks it
  ``working``, and finalizes it (``completed`` / ``failed`` / ``input-required``)
  from the dispatch result.

Parent linkage flows through context vars, so a (future) nested dispatch — an
agent that itself calls another agent — links to its caller's node rather than
the turn root, giving the hierarchical tree the design calls for.

See ``docs/dev-docs/background-tasks.md``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterable, List, Optional

import task_graph

logger = logging.getLogger(__name__)


def background_deadline_seconds() -> float:
    """Soft deadline after which a slow turn is promoted to a background task.

    ``PROMETHEUS_BACKGROUND_DEADLINE_SECONDS`` <= 0 (the default) disables
    backgrounding entirely, preserving the synchronous request/response flow.
    """
    raw = os.getenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _new_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


def _clean_title(title: str, limit: int = 80) -> str:
    text = " ".join(str(title or "").split()).strip()
    if not text:
        return "request"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def new_turn_id() -> str:
    """A turn id, distinct from Task Graph ``t_`` ids."""
    return f"turn_{uuid.uuid4().hex[:12]}"


class _Turn:
    __slots__ = (
        "conversation_id",
        "title",
        "root_id",
        "created",
        "background_requested",
        "turn_id",
        "started_at",
        "produced_artifact_ids",
    )

    def __init__(self, conversation_id: str, title: str) -> None:
        self.conversation_id = conversation_id
        self.title = title
        self.root_id = _new_id()
        self.created = False
        # ``root_id`` is the Task Graph handle and a resume rewrites it (see
        # ``track_skill``); ``turn_id`` names this turn and never changes. It tags
        # the turn's history entries and the artifacts it produced.
        self.turn_id = new_turn_id()
        self.started_at = time.time()
        # Artifact ids this turn's own dispatches and uploads produced, in arrival
        # order. The turn's ``new_artifacts`` come from this list, never from a
        # catalog diff, so a turn running in parallel cannot leak into it.
        self.produced_artifact_ids: List[str] = []
        # Set when a dispatched agent declares itself long-running (proactive
        # detach). The turn object is created once per turn and shared by
        # reference into the detached chat() task's copied context, so a deep
        # call setting this event is observed by the waiter in service._execute.
        self.background_requested = asyncio.Event()


_turn: ContextVar[Optional[_Turn]] = ContextVar("task_turn", default=None)
_nested_parent: ContextVar[Optional[str]] = ContextVar("task_nested_parent", default=None)


# --- turn lifecycle ----------------------------------------------------------


def begin_turn(conversation_id: str, title: str) -> None:
    """Register a new turn. The root node is materialized on first dispatch."""
    conv = str(conversation_id or "")
    _turn.set(_Turn(conv, _clean_title(title)) if conv else None)


def _ensure_root() -> Optional[str]:
    turn = _turn.get()
    if turn is None:
        return None
    if not turn.created:
        try:
            task_graph.create_node(
                task_id=turn.root_id,
                conversation_id=turn.conversation_id,
                title=turn.title,
            )
            task_graph.update_own_state(turn.conversation_id, turn.root_id, own_state="working")
            turn.created = True
        except Exception as exc:
            logger.warning("[TASKTRACK] Failed to create root node: %s", exc)
            return None
    return turn.root_id


def current_root_id() -> Optional[str]:
    turn = _turn.get()
    return turn.root_id if turn is not None else None


def current_turn() -> Optional[_Turn]:
    """The current turn, or ``None`` outside one (slash commands)."""
    return _turn.get()


def current_turn_id() -> Optional[str]:
    turn = _turn.get()
    return turn.turn_id if turn is not None else None


def record_produced_artifacts(artifact_ids: Iterable[Optional[str]]) -> None:
    """Add artifact ids to the current turn's produced list. No-op outside a turn.

    Called with the ids of every A2A artifact a dispatch returns (see
    ``tool_discovery.call_a2a_agent``) and with the ids of the turn's uploads. The
    turn object is shared by reference into the detached ``chat()`` task and its
    ``asyncio.gather`` children, so their ids land on the same list.
    """
    turn = _turn.get()
    if turn is None:
        return
    for artifact_id in artifact_ids:
        if artifact_id and str(artifact_id) not in turn.produced_artifact_ids:
            turn.produced_artifact_ids.append(str(artifact_id))


def background_event() -> Optional[asyncio.Event]:
    """The current turn's proactive-detach signal, or ``None`` outside a turn.

    ``service._execute`` races ``chat()`` against this event so an agent that
    calls ``declare_long_running`` detaches the turn immediately, regardless of
    the soft-deadline setting.
    """
    turn = _turn.get()
    return turn.background_requested if turn is not None else None


def request_background(node_id: Optional[str] = None) -> None:
    """Signal that the current turn should detach now (an agent declared itself
    long-running). Idempotent. Also flags the dispatched skill node — and the
    turn root — as background so ``/tasks`` and percolation reflect it."""
    turn = _turn.get()
    if turn is None:
        return
    turn.background_requested.set()
    node_id = node_id or _nested_parent.get()
    for tid in (node_id, turn.root_id if turn.created else None):
        if not tid:
            continue
        try:
            task_graph.update_own_state(turn.conversation_id, tid, is_background=True)
        except Exception as exc:
            logger.warning("[TASKTRACK] Failed to flag background node %s: %s", tid, exc)


def _own_state_for_status(status: str) -> Optional[str]:
    """Map an orchestrator response status to the root node's own state.

    A ``needs_info`` turn has finished its own orchestration work. Its
    input-required child keeps the root's effective state non-terminal until
    that exact child is resumed and completed.
    """
    state = (status or "").strip().lower()
    if state == "error":
        return "failed"
    if state in ("completed", "answer", "needs_info"):
        return "completed"
    return None


def finish_turn(status: str) -> None:
    """Resolve the current turn's root node based on the response status."""
    turn = _turn.get()
    if turn is None or not turn.created:
        return
    finish_turn_for(turn.conversation_id, turn.root_id, status)


def finish_turn_for(conversation_id: str, root_id: Optional[str], status: str) -> None:
    """Resolve a specific root node — used by the detached background finisher,
    which runs outside the originating request's context vars."""
    if not conversation_id or not root_id:
        return
    own = _own_state_for_status(status)
    if own is None:
        return
    try:
        task_graph.update_own_state(conversation_id, root_id, own_state=own)
    except Exception as exc:
        logger.warning("[TASKTRACK] Failed to finalize root node: %s", exc)


def ensure_background_root() -> Optional[str]:
    """Materialize the turn root (if not already) and flag it as backgrounded.

    Called when a turn is detached so there is always a trackable node, even if
    the slowness was in orchestration rather than a tracked skill dispatch.
    """
    root_id = _ensure_root()
    if root_id is None:
        return None
    turn = _turn.get()
    try:
        task_graph.update_own_state(
            turn.conversation_id, root_id, own_state="working", is_background=True
        )
    except Exception as exc:
        logger.warning("[TASKTRACK] Failed to flag background root: %s", exc)
    return root_id


async def run_background_finish(
    *,
    chat_task: Awaitable[Any],
    conversation_id: str,
    root_id: Optional[str],
    build_payload: Callable[[Any], Dict[str, Any]],
    on_status: Optional[Callable[[str], None]] = None,
) -> None:
    """Await a detached orchestration task, then finalize its Task Graph root and
    persist the result so the frontend can render it on completion.

    Kept here (rather than in service.py) so it depends only on task_graph and is
    unit-testable without importing the heavy orchestrator/prometheus_api stack.
    """
    try:
        response = await chat_task
    except Exception as exc:
        if root_id:
            try:
                task_graph.update_own_state(
                    conversation_id, root_id, own_state="failed", error=str(exc)
                )
            except Exception:
                pass
        if on_status:
            on_status(f"Background task failed: {exc}")
        return

    try:
        payload = build_payload(response)
        task_graph.store_result(conversation_id, root_id or "", payload)
    except Exception as exc:
        logger.warning("[TASKTRACK] Failed to store background result: %s", exc)

    finish_turn_for(conversation_id, root_id, getattr(response, "status", "") or "")
    if on_status:
        on_status("Background task complete.")


# --- per-skill tracking ------------------------------------------------------


class SkillTracker:
    """Mutable outcome holder for one tracked skill dispatch."""

    def __init__(self, conversation_id: str, node_id: str) -> None:
        self._conversation_id = conversation_id
        self._node_id = node_id
        self._state = "completed"
        self._message: Optional[str] = None
        self._result_ref: Optional[str] = None
        self._error: Optional[str] = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def active(self) -> bool:
        return bool(self._node_id)

    def progress(self, message: str) -> None:
        """Emit an interim status while the skill runs."""
        if not self._node_id:
            return
        try:
            task_graph.update_own_state(
                self._conversation_id, self._node_id, own_state="working", message=message
            )
        except Exception as exc:
            logger.warning("[TASKTRACK] progress update failed: %s", exc)

    def complete(self, *, result_ref: Optional[str] = None, message: Optional[str] = None) -> None:
        self._state = "completed"
        self._result_ref = result_ref
        self._message = message

    def fail(self, error: Any) -> None:
        self._state = "failed"
        self._error = str(error)

    def input_required(self) -> None:
        self._state = "input-required"


def _finalize(tracker: SkillTracker) -> None:
    if not tracker.active:
        return
    try:
        task_graph.update_own_state(
            tracker._conversation_id,
            tracker._node_id,
            own_state=tracker._state,
            message=tracker._message,
            result_ref=tracker._result_ref,
            error=tracker._error,
        )
    except Exception as exc:
        logger.warning("[TASKTRACK] Failed to finalize skill node: %s", exc)


@asynccontextmanager
async def track_skill(
    conversation_id: str,
    skill_id: str,
    *,
    agent: Optional[str] = None,
    title: Optional[str] = None,
    resume_node_id: Optional[str] = None,
    resume_root_id: Optional[str] = None,
) -> AsyncIterator[SkillTracker]:
    """Create or resume a Task Graph child node around a skill dispatch."""
    conv = str(conversation_id or "")
    if not conv:
        yield SkillTracker("", "")  # tracking disabled (no conversation scope)
        return

    if bool(resume_node_id) != bool(resume_root_id):
        raise ValueError("Task Graph resumption requires both node and root IDs")

    if resume_node_id and resume_root_id:
        node = task_graph.get_node(conv, resume_node_id)
        if node is None:
            raise ValueError(f"Task Graph resume node '{resume_node_id}' does not exist")
        if node.skill != skill_id:
            raise ValueError(
                f"Task Graph resume node '{resume_node_id}' belongs to skill "
                f"'{node.skill}', not '{skill_id}'"
            )
        if node.own_state != "input-required":
            raise ValueError(
                f"Task Graph resume node '{resume_node_id}' is '{node.own_state}', "
                "not 'input-required'"
            )

        actual_root_id = node.task_id
        seen: set[str] = set()
        while node.parent_task_id:
            if node.task_id in seen:
                raise ValueError(f"Task Graph cycle detected at '{node.task_id}'")
            seen.add(node.task_id)
            parent = task_graph.get_node(conv, node.parent_task_id)
            if parent is None:
                raise ValueError(
                    f"Task Graph resume node '{resume_node_id}' has missing parent "
                    f"'{node.parent_task_id}'"
                )
            node = parent
            actual_root_id = node.task_id
        if actual_root_id != resume_root_id:
            raise ValueError(
                f"Task Graph resume node '{resume_node_id}' belongs to root "
                f"'{actual_root_id}', not '{resume_root_id}'"
            )

        turn = _turn.get()
        if turn is not None:
            if turn.conversation_id != conv:
                raise ValueError(
                    f"Task Graph turn belongs to conversation '{turn.conversation_id}', "
                    f"not '{conv}'"
                )
            if turn.created and turn.root_id != resume_root_id:
                raise ValueError(
                    f"Task Graph turn already uses root '{turn.root_id}', "
                    f"not '{resume_root_id}'"
                )
            turn.root_id = resume_root_id
            turn.created = True

        node_id = resume_node_id
        if task_graph.update_own_state(conv, node_id, own_state="working") is None:
            raise ValueError(f"Task Graph resume node '{resume_node_id}' disappeared")
    else:
        parent = _nested_parent.get() or _ensure_root()
        node_id = _new_id()
        try:
            task_graph.create_node(
                task_id=node_id,
                conversation_id=conv,
                parent_task_id=parent,
                agent=agent,
                skill=skill_id,
                title=title or skill_id,
            )
            task_graph.update_own_state(conv, node_id, own_state="working")
        except Exception as exc:
            logger.warning("[TASKTRACK] Failed to create skill node: %s", exc)
            yield SkillTracker(conv, "")
            return

    tracker = SkillTracker(conv, node_id)
    token = _nested_parent.set(node_id)
    try:
        yield tracker
    except Exception as exc:
        tracker.fail(exc)
        raise
    finally:
        _nested_parent.reset(token)
        _finalize(tracker)


def apply_result_outcome(tracker: SkillTracker, result: Dict[str, Any]) -> None:
    """Map an ``invoke_skill`` result dict onto the tracker's outcome."""
    if not isinstance(result, dict):
        tracker.complete()
        return
    if "input_required" in result:
        tracker.input_required()
    elif result.get("error"):
        tracker.fail(result.get("error"))
    else:
        tracker.complete(result_ref=_first_artifact_ref(result.get("result")))


def _first_artifact_ref(result_payload: Any) -> Optional[str]:
    """Best-effort extraction of an artifact id from a skill result."""
    if not isinstance(result_payload, dict):
        return None
    artifacts = result_payload.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        first = artifacts[0]
        if isinstance(first, dict):
            ref = first.get("artifact_id") or first.get("id") or first.get("uri")
            return str(ref) if ref else None
    return None
