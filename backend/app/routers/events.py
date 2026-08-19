"""GET /api/events — the per-session SSE stream (decision D2).

One long-lived ``text/event-stream`` per browser session. It multiplexes two
producers onto a single connection:

- ``status`` frames for the in-flight turn (published by ``routers/chat.py`` via
  the :class:`~app.services.events.EventBus`), replacing Chainlit's ``cl.Step``.
- ``task_progress`` / ``task_done`` frames for backgrounded tasks, produced by the
  Redis subscriber this endpoint owns for the connection's lifetime
  (:func:`~app.services.events.run_task_subscriber`).

The subscriber task is started on connect and cancelled on disconnect so a closed
browser tab never leaks a Redis subscription. Heartbeat comments keep intermediaries
(and the browser's ``EventSource``) from timing the idle connection out.

Infra note: this route must not be buffered — nginx needs ``proxy_buffering off``
and a long ``proxy_read_timeout`` (task 09).
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.contract import ServerEvent
from app.security import TokenClaims, current_claims
from app.services.events import EventBus, run_task_subscriber
from app.sessions import SessionState, SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

# Idle heartbeat cadence (seconds). Sent as an SSE comment when no real event
# arrives within the window, so the connection survives idle turns.
_HEARTBEAT_SECONDS = 15.0


def _get_store(request: Request) -> SessionStore:
    return cast(SessionStore, request.app.state.session_store)


def _get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


def _sse_frame(event: ServerEvent) -> str:
    """Render one typed event as an SSE ``event:``/``data:`` frame.

    The event name is the model's ``type`` discriminator so the browser can
    ``addEventListener("status" | "task_progress" | "task_done", …)``.
    """
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


async def _event_stream(
    request: Request,
    bus: EventBus,
    session: SessionState,
) -> AsyncIterator[str]:
    """Drain the session's queue as SSE, heart-beating through idle gaps.

    Registers a fresh bus queue for this connection, starts the background-task
    Redis subscriber, and yields frames until the client disconnects — at which
    point the subscriber is cancelled and the queue unregistered.
    """
    queue = bus.register(session.sid)
    # One background-task subscriber per session, shared across connections/tabs (T-5):
    # start it only for the first connection of this sid; the last to close cancels it.
    # (Publishing fans out to every queue for the sid, so one subscriber feeds all tabs
    # exactly once — two subscribers would duplicate every task_progress event.)
    if bus.get_task_subscriber(session.sid) is None:
        task = asyncio.create_task(
            run_task_subscriber(
                bus,
                session,
                settings.redis_url,
                auto_approve=settings.auto_approve_steps,
            )
        )
        bus.set_task_subscriber(session.sid, task)
    try:
        # Open the stream immediately so the client's EventSource fires `open`
        # before any real event (and so proxies flush the response headers).
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield _sse_frame(event)
    finally:
        bus.unregister(session.sid, queue)
        # Tear the shared subscriber down only when this sid's last stream closes.
        if bus.listener_count(session.sid) == 0:
            subscriber = bus.get_task_subscriber(session.sid)
            bus.clear_task_subscriber(session.sid)
            if subscriber is not None:
                subscriber.cancel()
                try:
                    await subscriber
                except (asyncio.CancelledError, Exception):  # noqa: BLE001 - cleanup only
                    pass


@router.get("/events")
async def events(
    request: Request,
    claims: TokenClaims = Depends(current_claims),
) -> StreamingResponse:
    """Open the session's SSE stream. Auth-required; one per browser connection."""
    store = _get_store(request)
    session = store.get_or_create(claims.sid)
    bus = _get_event_bus(request)

    return StreamingResponse(
        _event_stream(request, bus, session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # belt-and-suspenders for nginx buffering
        },
    )
