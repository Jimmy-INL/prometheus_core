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

import logging
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Dict, Optional

import task_graph

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


def _clean_title(title: str, limit: int = 80) -> str:
    text = " ".join(str(title or "").split()).strip()
    if not text:
        return "request"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Turn:
    __slots__ = ("conversation_id", "title", "root_id", "created")

    def __init__(self, conversation_id: str, title: str) -> None:
        self.conversation_id = conversation_id
        self.title = title
        self.root_id = _new_id()
        self.created = False


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


def finish_turn(status: str) -> None:
    """Resolve the turn root based on the orchestrator response status.

    ``needs_info`` / ``plan_ready`` / ``backgrounded`` intentionally leave the
    root non-terminal: the turn is paused, not done.
    """
    turn = _turn.get()
    if turn is None or not turn.created:
        return
    state = (status or "").strip().lower()
    if state == "error":
        own = "failed"
    elif state in ("completed", "answer"):
        own = "completed"
    else:
        return  # paused — leave the root working
    try:
        task_graph.update_own_state(turn.conversation_id, turn.root_id, own_state=own)
    except Exception as exc:
        logger.warning("[TASKTRACK] Failed to finalize root node: %s", exc)


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
) -> AsyncIterator[SkillTracker]:
    """Create and finalize a Task Graph child node around a skill dispatch."""
    conv = str(conversation_id or "")
    if not conv:
        yield SkillTracker("", "")  # tracking disabled (no conversation scope)
        return

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
