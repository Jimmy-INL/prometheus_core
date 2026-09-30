"""Conversation state persistence for the client-agent."""

import json
from typing import Any, Dict, Iterable, List, Optional

import redis
from prometheus_api.redis_utils import create_redis_client

_conversation_store_client: Optional[redis.Redis] = None


def _get_conversation_store_client() -> redis.Redis:
    """Get or create the singleton Redis client for conversation storage."""
    global _conversation_store_client
    if _conversation_store_client is None:
        _conversation_store_client = create_redis_client(ping=False)
        if _conversation_store_client is None:
            raise RuntimeError("Redis client could not be created; check REDIS_URL/REDIS_PASSWORD")
    return _conversation_store_client


def store_conversation(conv_id: str, state: Dict[str, Any]) -> None:
    """Persist a conversation state document."""
    _get_conversation_store_client().set(
        f"conversation:{conv_id}",
        json.dumps(state, default=str),
    )


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    """Load a conversation state document."""
    data = _get_conversation_store_client().get(f"conversation:{conv_id}")
    return json.loads(data) if data else None


def stamp_turn_artifacts(
    history: List[Dict[str, Any]],
    artifact_ids: Iterable[str],
    texts: Iterable[Optional[str]],
) -> bool:
    """Record on a turn's assistant entry which artifacts that turn produced.

    A restored conversation renders each turn from these ids, never from the whole
    conversation catalog (Prometheus Artifact Contract, "Frontend viewer ownership").
    The target is the newest assistant entry whose ``content`` is one of *texts* (the
    turn's reply). No match means no stamp: some responses write no history entry (a
    plan rejection, the "running in the background" notice), and guessing the newest
    entry would put this turn's artifacts under an older reply. Ids already on the
    entry are kept, so a turn stamped twice loses nothing. Returns whether *history*
    changed.
    """
    ids = [str(i) for i in artifact_ids if i]
    replies = {str(t) for t in texts if t}
    if not ids or not replies:
        return False
    matching = [
        e for e in history
        if isinstance(e, dict) and e.get("role") == "assistant" and str(e.get("content") or "") in replies
    ]
    if not matching:
        return False
    entry = matching[-1]
    existing = [str(i) for i in entry.get("artifact_ids") or []]
    merged = existing + [i for i in ids if i not in existing]
    if merged == existing:
        return False
    entry["artifact_ids"] = merged
    return True


def record_turn_artifacts(
    conv_id: str,
    artifact_ids: Iterable[str],
    texts: Iterable[Optional[str]],
) -> None:
    """Stamp *artifact_ids* onto the stored ``conversation:{id}`` history.

    Runs after the turn's ``chat()`` has stored the conversation, so the reply entry
    is already there. See :func:`stamp_turn_artifacts`.
    """
    state = get_conversation(conv_id)
    if not state:
        return
    history = state.get("conversation_history")
    if isinstance(history, list) and stamp_turn_artifacts(history, artifact_ids, texts):
        store_conversation(conv_id, state)
