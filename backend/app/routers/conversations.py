"""GET /api/conversations/recent — Redis-backed conversation history.

Replaces the Chainlit ``/history`` slash command (``_handle_conversation_history``,
frontend/main.py:107): returns recent conversation summaries as JSON instead of a
markdown ``cl.Message``. Slash-command parsing is now a frontend concern.

``ConversationStateClient`` (app/conversation_state.py, lifted in task 03) uses the
**synchronous** redis client, so its calls are offloaded to a worker thread with
``asyncio.to_thread`` to keep the event loop free. When Redis is unreachable the
endpoint degrades to ``{available: false, conversations: []}`` with a 200.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.contract import ConversationHistoryResponse, ConversationSummary
from app.conversation_state import ConversationStateClient
from app.security import TokenClaims, current_claims

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["conversations"])


# One client reused across requests (AU-7): ConversationStateClient caches its Redis
# connection, so a shared instance avoids a fresh connect + ping per call. Keyed on the
# class object (not id()) so tests monkeypatching ``ConversationStateClient`` get their
# own instance without id-reuse hazards, while the class is kept alive as the cache key.
_client_cache: dict = {}


def _client() -> ConversationStateClient:
    cls = ConversationStateClient
    inst = _client_cache.get(cls)
    if inst is None:
        inst = cls(settings.redis_url)
        _client_cache[cls] = inst
    return inst


def _fetch_recent(limit: int) -> tuple[bool, list[dict]]:
    """Blocking Redis read, run in a worker thread.

    Returns ``(available, rows)``: ``available`` distinguishes "Redis down" from
    "Redis up but empty" (both yield an empty ``rows``).
    """
    client = _client()
    if not client.available:
        return False, []
    return True, client.get_conversation_history(limit=limit)


@router.get("/conversations/recent", response_model=ConversationHistoryResponse)
async def get_recent_conversations(
    limit: int = Query(20, ge=1, le=100),
    claims: TokenClaims = Depends(current_claims),
) -> ConversationHistoryResponse:
    available, rows = await asyncio.to_thread(_fetch_recent, limit)
    return ConversationHistoryResponse(
        available=available,
        conversations=[ConversationSummary(**row) for row in rows],
    )
