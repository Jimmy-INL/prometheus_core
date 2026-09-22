"""Valkey-backed per-session state store.

Replaces Chainlit's ``cl.user_session``. Each entry is keyed by the JWT ``sid``
(one per login) and mirrors the keys the Chainlit app kept on ``cl.user_session``:

    cl.user_session key         SessionState field
    ------------------------    ------------------
    conversation_id             conversation_id
    artifacts                   artifacts
    backgrounded_task_ids       awaited_task_ids
    chat_profile                profile

State lives in Valkey, not in this process, so it survives a backend restart and is
identical across ``uvicorn --workers N`` (see ``backend/README.md``). Two keys per
session, both carrying the cookie's TTL, refreshed on every write — no reaper:

    session:{sid}           HASH  conversation_id, profile, consecutive_needs_info,
                                  artifacts (JSON array)
    session:{sid}:awaited   SET   root task ids the session is waiting on

**:class:`SessionState` is a read-only snapshot.** It used to be the live object every
caller mutated in place (``session.awaited_task_ids.add(...)``,
``session.consecutive_needs_info += 1``), which only worked because there was exactly
one process holding exactly one copy. A snapshot cannot observe those, and silently
dropping a write is the worst possible failure here — so the dataclass is ``frozen``
and ``awaited_task_ids`` is a ``frozenset``. Every former mutation is now an explicit
``SessionStore`` coroutine below, and anything this migration missed raises
``FrozenInstanceError``/``AttributeError`` rather than quietly losing state.

:meth:`SessionStore.claim_task` deserves its own note: the exactly-once guarantee for
background-task completion used to be a check-then-discard against an in-process set,
safe only because of the single process. It is now a single ``SREM`` whose return count
*is* the claim — atomic, and correct across workers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, cast

from fastapi import Request

from app.config import settings
from redis.typing import FieldT

from app.redis_client import RedisClient

logger = logging.getLogger(__name__)


#: One ``session:{sid}`` hash field write. Keyed by ``redis.typing.FieldT`` rather than
#: ``str`` because ``Mapping`` is invariant in its key type, so ``dict[str, ...]`` is not
#: accepted by ``hset(mapping=...)``. Values stay narrow (``str``/``int``) so a
#: non-encodable one -- a list, a dataclass -- is caught here and not by redis-py at run
#: time; every field is stored as a string, ints included.
SessionFields = dict[FieldT, str | int]


def _hash_key(sid: str) -> str:
    return f"session:{sid}"


def _awaited_key(sid: str) -> str:
    return f"session:{sid}:awaited"


@dataclass(frozen=True)
class SessionState:
    """Read-only snapshot of one logged-in browser session.

    Frozen on purpose: see the module docstring. To change session state, call the
    corresponding :class:`SessionStore` coroutine; assigning to a field here raises.
    """

    sid: str
    conversation_id: Optional[str] = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    awaited_task_ids: frozenset[str] = field(default_factory=frozenset)
    profile: str = ""
    # Count of consecutive ``needs_info`` turns, for the follow-up depth cap (T-2).
    # Incremented on each needs_info response, reset on any other terminal status.
    consecutive_needs_info: int = 0


def _decode_artifacts(raw: Optional[str]) -> list[dict[str, Any]]:
    """Parse the stored artifacts JSON, treating any corruption as "no catalog".

    A malformed value would only ever come from a hand-edited key or a half-written
    value, and the cost of tolerating it is that ``GET /api/artifacts/{id}/content``
    can't resolve ids until the next turn rewrites the catalog — far better than
    500-ing every request the session makes from then on.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("session: discarding unparseable artifacts catalog")
        return []
    return [a for a in parsed if isinstance(a, dict)] if isinstance(parsed, list) else []


class SessionStore:
    """Valkey-backed session registry keyed by ``sid``.

    Holds no state of its own beyond the client, so constructing one per request (or
    one per process, as ``main.py`` does) is equivalent.
    """

    def __init__(self, redis: RedisClient, *, ttl_seconds: Optional[int] = None) -> None:
        self._redis = redis
        # Session state is worthless once the cookie that names it has expired, so the
        # two keys carry the token TTL and are refreshed on every write.
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.token_ttl_seconds

    # -- reads -------------------------------------------------------------- #

    async def get(self, sid: str) -> Optional[SessionState]:
        """Snapshot of ``sid``, or ``None`` if the session has no stored state."""
        pipe = self._redis.pipeline()
        pipe.hgetall(_hash_key(sid))
        pipe.smembers(_awaited_key(sid))
        fields, awaited = await pipe.execute()
        if not fields and not awaited:
            return None
        return self._snapshot(sid, fields or {}, awaited or set())

    async def get_or_create(self, sid: str) -> SessionState:
        """Snapshot of ``sid``, defaulting to an empty session.

        Nothing is written: Redis has no empty hash, so "registered but untouched"
        and "absent" are the same state, and both mean the defaults below. The login
        routes call this purely to assert the sid is usable.
        """
        state = await self.get(sid)
        return state if state is not None else SessionState(sid=sid)

    def _snapshot(self, sid: str, fields: dict[str, Any], awaited: Any) -> SessionState:
        try:
            needs_info = int(fields.get("consecutive_needs_info") or 0)
        except (TypeError, ValueError):
            needs_info = 0
        return SessionState(
            sid=sid,
            conversation_id=fields.get("conversation_id") or None,
            artifacts=_decode_artifacts(fields.get("artifacts")),
            awaited_task_ids=frozenset(str(t) for t in awaited),
            profile=fields.get("profile") or "",
            consecutive_needs_info=needs_info,
        )

    # -- writes ------------------------------------------------------------- #

    async def _write(self, sid: str, fields: SessionFields) -> None:
        pipe = self._redis.pipeline()
        pipe.hset(_hash_key(sid), mapping=fields)
        pipe.expire(_hash_key(sid), self._ttl)
        await pipe.execute()

    async def set_conversation(self, sid: str, conversation_id: str) -> None:
        """Bind the session to ``conversation_id`` without touching anything else."""
        await self._write(sid, {"conversation_id": conversation_id})

    async def set_profile(self, sid: str, profile: str) -> None:
        await self._write(sid, {"profile": profile})

    async def set_artifacts(self, sid: str, artifacts: list[dict[str, Any]]) -> None:
        """Replace the conversation's artifact catalog (task 07 resolves ids from it)."""
        await self._write(sid, {"artifacts": json.dumps(artifacts)})

    async def reset(
        self,
        sid: str,
        conversation_id: str,
        *,
        profile: Optional[str] = None,
        artifacts: Optional[list[dict[str, Any]]] = None,
        keep_awaited: bool = False,
    ) -> None:
        """Rebind the session to a conversation, clearing per-conversation state.

        The "New chat" / history-resume path: a different conversation starts with no
        artifact catalog, no awaited background tasks and no follow-up depth. One
        pipeline so a concurrent reader can't see the new conversation id alongside the
        old conversation's artifacts.

        ``artifacts`` seeds the catalog in the same pipeline -- the resume path already
        holds the (mesh-enriched) list and would otherwise write ``[]`` and immediately
        overwrite it, leaving a window where the content proxy 404s every artifact.

        ``keep_awaited`` preserves the awaited-task set, which is only ever correct when
        rebinding to the conversation the session is *already* on: the set holds root
        task ids, and every lookup of one (``task_events.fetch_result``, the subscriber's
        channel) is scoped by conversation id, so an id carried across a switch would
        resolve against the wrong conversation.
        """
        fields: SessionFields = {
            "conversation_id": conversation_id,
            "artifacts": json.dumps(artifacts if artifacts is not None else []),
            "consecutive_needs_info": 0,
        }
        if profile is not None:
            fields["profile"] = profile
        pipe = self._redis.pipeline()
        pipe.hset(_hash_key(sid), mapping=fields)
        pipe.expire(_hash_key(sid), self._ttl)
        if not keep_awaited:
            pipe.delete(_awaited_key(sid))
        await pipe.execute()

    async def drop(self, sid: str) -> None:
        """Forget a session (e.g. on logout). Idempotent."""
        await self._redis.delete(_hash_key(sid), _awaited_key(sid))

    # -- follow-up depth cap (T-2) ------------------------------------------ #

    async def bump_needs_info(self, sid: str) -> int:
        """Increment and return the consecutive-``needs_info`` counter (``HINCRBY``)."""
        pipe = self._redis.pipeline()
        pipe.hincrby(_hash_key(sid), "consecutive_needs_info", 1)
        pipe.expire(_hash_key(sid), self._ttl)
        count, _ = await pipe.execute()
        return int(count)

    async def reset_needs_info(self, sid: str) -> None:
        await self._write(sid, {"consecutive_needs_info": 0})

    # -- awaited background tasks ------------------------------------------- #

    async def await_task(self, sid: str, task_id: str) -> None:
        """Register a backgrounded root task id for this session (``SADD``)."""
        pipe = self._redis.pipeline()
        pipe.sadd(_awaited_key(sid), task_id)
        pipe.expire(_awaited_key(sid), self._ttl)
        await pipe.execute()

    async def claim_task(self, sid: str, task_id: str) -> bool:
        """Atomically consume ``task_id``; ``True`` for exactly one caller.

        ``SREM`` returns the number of members actually removed, so the winner of a
        race between the subscriber loop, the fast-finish guard and the router's
        reconcile gets ``1`` and everyone else gets ``0``. Pair a ``False`` return
        with "someone else announced it", and restore a claim you could not honour
        with :meth:`await_task`.
        """
        removed = await self._redis.srem(_awaited_key(sid), task_id)
        return bool(removed)

    async def is_awaiting(self, sid: str, task_id: str) -> bool:
        """Whether ``task_id`` is still awaited. A hint only — :meth:`claim_task` is
        the authority, since this can go stale the moment it returns."""
        return bool(await self._redis.sismember(_awaited_key(sid), task_id))


def get_store(request: Request) -> SessionStore:
    """Look up the process-wide :class:`SessionStore` off app state.

    Shared by every router that touches session state, so there's one place that
    knows where it lives.
    """
    return cast(SessionStore, request.app.state.session_store)
