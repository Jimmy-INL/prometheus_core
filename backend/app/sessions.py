"""In-memory per-session state store.

Replaces Chainlit's ``cl.user_session``. Each entry is keyed by the JWT ``sid``
(one per login) and mirrors the keys the Chainlit app kept on ``cl.user_session``:

    cl.user_session key         SessionState field
    ------------------------    ------------------
    conversation_id             conversation_id
    artifacts                   artifacts
    backgrounded_task_ids       awaited_task_ids
    chat_profile                profile

State lives only in this process's memory and is **lost on restart** — same
volatility as ``cl.user_session`` today. When the backend is scaled to multiple
workers/replicas this must move to Redis; until then a single process is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, cast

from fastapi import Request


@dataclass
class SessionState:
    """Mutable per-session state for one logged-in browser session."""

    sid: str
    conversation_id: Optional[str] = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    awaited_task_ids: set[str] = field(default_factory=set)
    profile: str = ""
    # Count of consecutive ``needs_info`` turns, for the follow-up depth cap (T-2).
    # Incremented on each needs_info response, reset on any other terminal status.
    consecutive_needs_info: int = 0


class SessionStore:
    """Dict-backed session registry keyed by ``sid``.

    Not thread-safe by design: the app runs on a single asyncio event loop and
    these operations are synchronous and non-yielding, so no lock is needed.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, sid: str) -> Optional[SessionState]:
        return self._sessions.get(sid)

    def get_or_create(self, sid: str) -> SessionState:
        state = self._sessions.get(sid)
        if state is None:
            state = SessionState(sid=sid)
            self._sessions[sid] = state
        return state

    def drop(self, sid: str) -> None:
        """Forget a session (e.g. on logout). Idempotent."""
        self._sessions.pop(sid, None)

    def __len__(self) -> int:
        return len(self._sessions)


def get_store(request: Request) -> SessionStore:
    """Look up the process-wide :class:`SessionStore` off app state.

    Shared by every router that registers a session id on login (``routers/auth.py``,
    ``routers/setup.py``) so there's one place that knows where it lives.
    """
    return cast(SessionStore, request.app.state.session_store)
