"""Offline tests for the SSE events service (task 05).

Exercise the in-process :class:`EventBus`, the ``run_task_notifier`` port
(root-vs-child filtering, idempotent completion, fast-finish guard, progress
dedup), and the ``GET /api/events`` endpoint's frame shaping — all with
``task_events`` monkeypatched, no live Redis.
"""

import asyncio

import pytest

from app import task_events
from app.contract import StatusEvent, TaskDoneEvent, TaskProgressEvent
from app.services import events as events_service
from app.services.events import EventBus, run_task_subscriber
from app.sessions import SessionState


def _session(*, sid: str = "sid-1", **kwargs) -> SessionState:
    return SessionState(sid=sid, conversation_id="c1", **kwargs)


async def _drain(queue: "asyncio.Queue", n: int) -> list:
    return [await asyncio.wait_for(queue.get(), timeout=1.0) for _ in range(n)]


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #


async def test_bus_fans_out_to_all_queues_for_sid():
    bus = EventBus()
    q1 = bus.register("sid-1")
    q2 = bus.register("sid-1")
    other = bus.register("sid-2")

    await bus.publish("sid-1", StatusEvent(turn_id="t1", message="hi"))

    assert (await q1.get()).message == "hi"
    assert (await q2.get()).message == "hi"
    assert other.empty()


async def test_bus_publish_with_no_subscribers_is_noop():
    bus = EventBus()
    # Must not raise even though nobody is listening.
    await bus.publish("nobody", StatusEvent(turn_id="t", message="x"))


async def test_bus_unregister_drops_sid_when_last_queue_closes():
    bus = EventBus()
    q = bus.register("sid-1")
    bus.unregister("sid-1", q)
    assert "sid-1" not in bus._subscribers


# --------------------------------------------------------------------------- #
# run_task_subscriber — completion, filtering, dedup
# --------------------------------------------------------------------------- #


def _patch_task_events(
    monkeypatch,
    *,
    events_seq=(),
    result=None,
    snapshot=None,
):
    """Stub the Redis-backed task_events surface used by the subscriber."""

    async def _subscribe(redis_url, conversation_id):
        for event in events_seq:
            yield event

    async def _fetch_result(redis_url, conversation_id, task_id):
        return result

    async def _node_snapshot(redis_url, conversation_id, task_id):
        return snapshot

    monkeypatch.setattr(task_events, "subscribe", _subscribe)
    monkeypatch.setattr(task_events, "fetch_result", _fetch_result)
    monkeypatch.setattr(task_events, "node_snapshot", _node_snapshot)


async def test_completed_event_emits_mapped_task_done(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"task-1"})

    _patch_task_events(
        monkeypatch,
        events_seq=[{"task_id": "task-1", "root_task_id": "task-1", "state": "completed"}],
        result={"conversation_id": "c1", "status": "answer", "response_text": "the answer"},
    )

    await run_task_subscriber(bus, session, "redis://x")

    (event,) = await _drain(queue, 1)
    assert isinstance(event, TaskDoneEvent)
    assert event.task_id == "task-1"
    assert event.state == "completed"
    assert event.response is not None
    assert event.response.response_text == "the answer"
    # Idempotency: the id is consumed once announced.
    assert "task-1" not in session.awaited_task_ids


async def test_non_completed_terminal_emits_bodyless_task_done(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"task-1"})

    _patch_task_events(
        monkeypatch,
        events_seq=[{"task_id": "task-1", "root_task_id": "task-1", "state": "failed"}],
    )

    await run_task_subscriber(bus, session, "redis://x")

    (event,) = await _drain(queue, 1)
    assert isinstance(event, TaskDoneEvent)
    assert event.state == "failed"
    assert event.response is None
    # E-5: a human-readable line accompanies the non-completed terminal event.
    assert event.message is not None and "failed" in event.message


async def test_child_and_unawaited_events_are_ignored(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"root-1"})

    _patch_task_events(
        monkeypatch,
        events_seq=[
            # child of root-1 → task_id != root_task_id → ignored
            {"task_id": "child-1", "root_task_id": "root-1", "state": "running", "message": "child work"},
            # a root we're not awaiting → ignored
            {"task_id": "root-2", "root_task_id": "root-2", "state": "completed"},
            # the real root progress → surfaced
            {"task_id": "root-1", "root_task_id": "root-1", "state": "running", "message": "step 1"},
        ],
        result={"conversation_id": "c1", "status": "answer"},
    )

    await run_task_subscriber(bus, session, "redis://x")

    (event,) = await _drain(queue, 1)
    assert isinstance(event, TaskProgressEvent)
    assert event.task_id == "root-1"
    assert event.message == "step 1"
    # root-1 never reached a terminal state, so it stays awaited.
    assert session.awaited_task_ids == {"root-1"}


async def test_progress_dedups_consecutive_repeats(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"root-1"})

    _patch_task_events(
        monkeypatch,
        events_seq=[
            {"task_id": "root-1", "root_task_id": "root-1", "state": "running", "message": "same"},
            {"task_id": "root-1", "root_task_id": "root-1", "state": "running", "message": "same"},
            {"task_id": "root-1", "root_task_id": "root-1", "state": "running", "message": ""},
            {"task_id": "root-1", "root_task_id": "root-1", "state": "running", "message": "next"},
        ],
    )

    await run_task_subscriber(bus, session, "redis://x")

    events = await _drain(queue, 2)
    assert [e.message for e in events] == ["same", "next"]
    assert queue.empty()


# --------------------------------------------------------------------------- #
# Fast-finish guard
# --------------------------------------------------------------------------- #


async def test_fast_finish_guard_announces_once(monkeypatch):
    """A task terminal before subscribe is announced by the guard, not twice."""
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"task-1"})

    # Snapshot already terminal; the live event stream ALSO carries the terminal
    # event. The guard should consume the id first so the loop can't re-announce.
    _patch_task_events(
        monkeypatch,
        events_seq=[{"task_id": "task-1", "root_task_id": "task-1", "state": "completed"}],
        result={"conversation_id": "c1", "status": "answer", "response_text": "done"},
        snapshot={"state": "completed"},
    )

    await run_task_subscriber(bus, session, "redis://x")

    events = await _drain(queue, 1)
    assert len(events) == 1
    assert isinstance(events[0], TaskDoneEvent)
    assert events[0].response.response_text == "done"
    assert queue.empty()


async def test_fast_finish_guard_seeds_initial_progress(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")
    session = _session(awaited_task_ids={"task-1"})

    _patch_task_events(
        monkeypatch,
        events_seq=[],  # no live events
        snapshot={"state": "running", "last_status_message": "warming up"},
    )

    await run_task_subscriber(bus, session, "redis://x")

    (event,) = await _drain(queue, 1)
    assert isinstance(event, TaskProgressEvent)
    assert event.message == "warming up"
    assert session.awaited_task_ids == {"task-1"}


async def test_history_limit_constant():
    assert events_service.BACKGROUND_STATUS_HISTORY_LIMIT == 50


# --------------------------------------------------------------------------- #
# E-2 — awaited id restored on failure/cancellation (not lost mid-announce)
# --------------------------------------------------------------------------- #


async def test_announce_restores_id_on_fetch_failure(monkeypatch):
    bus = EventBus()
    bus.register("sid-1")
    session = _session(awaited_task_ids={"task-1"})

    async def boom_fetch(redis_url, conversation_id, task_id):
        raise RuntimeError("redis down mid-fetch")

    monkeypatch.setattr(task_events, "fetch_result", boom_fetch)

    with pytest.raises(RuntimeError):
        await events_service._announce_completion(
            bus, session, "redis://x", "task-1", "completed", auto_approve=False
        )
    # The id is put back so a reconnecting subscriber's guard can retry (not lost).
    assert "task-1" in session.awaited_task_ids


# --------------------------------------------------------------------------- #
# E-3 — per-connection queue is bounded (drops oldest on overflow)
# --------------------------------------------------------------------------- #


async def test_event_queue_is_bounded_and_drops_oldest(monkeypatch):
    monkeypatch.setattr(events_service, "EVENT_QUEUE_MAXSIZE", 2)
    bus = EventBus()
    queue = bus.register("sid-1")

    for i in range(4):
        await bus.publish("sid-1", StatusEvent(turn_id="t", message=f"m{i}"))

    assert queue.qsize() == 2
    # Oldest (m0, m1) were dropped; the two newest remain in order.
    assert [(await queue.get()).message for _ in range(2)] == ["m2", "m3"]


# --------------------------------------------------------------------------- #
# T-4 — reconcile a fast-finished backgrounded task
# --------------------------------------------------------------------------- #


async def test_reconcile_announces_when_already_terminal(monkeypatch):
    bus = EventBus()
    queue = bus.register("sid-1")  # a stream is listening
    session = _session(awaited_task_ids={"task-1"})

    _patch_task_events(
        monkeypatch,
        snapshot={"state": "completed"},
        result={"conversation_id": "c1", "status": "answer", "response_text": "bg done"},
    )

    await events_service.reconcile_backgrounded(bus, session, "redis://x", "task-1", auto_approve=False)

    (event,) = await _drain(queue, 1)
    assert isinstance(event, TaskDoneEvent) and event.state == "completed"
    assert event.response is not None and event.response.response_text == "bg done"
    assert "task-1" not in session.awaited_task_ids


async def test_reconcile_is_noop_without_listeners(monkeypatch):
    bus = EventBus()  # no register → nobody listening
    session = _session(awaited_task_ids={"task-1"})

    _patch_task_events(monkeypatch, snapshot={"state": "completed"}, result={"status": "answer"})

    await events_service.reconcile_backgrounded(bus, session, "redis://x", "task-1", auto_approve=False)
    # Left awaited so the connect-time fast-finish guard catches it when the SSE opens.
    assert "task-1" in session.awaited_task_ids


# --------------------------------------------------------------------------- #
# T-5 — one background-task subscriber per session, shared across connections
# --------------------------------------------------------------------------- #


async def test_two_connections_share_one_subscriber(monkeypatch):
    from starlette.requests import Request

    from app.routers import events as events_router
    from app.routers.events import _event_stream

    starts = 0

    async def fake_subscriber(bus_arg, session_arg, redis_url, *, auto_approve=False):
        nonlocal starts
        starts += 1
        await asyncio.sleep(3600)  # stay alive until cancelled

    monkeypatch.setattr(events_router, "run_task_subscriber", fake_subscriber)

    bus = EventBus()
    session = _session(sid="sid-multi")
    scope = {"type": "http", "method": "GET", "headers": []}

    async def _receive():
        return {"type": "http.request"}

    s1 = _event_stream(Request(scope, _receive), bus, session)
    s2 = _event_stream(Request(scope, _receive), bus, session)
    assert await asyncio.wait_for(s1.__anext__(), 1.0) == ": connected\n\n"
    assert await asyncio.wait_for(s2.__anext__(), 1.0) == ": connected\n\n"
    await asyncio.sleep(0)  # let the created subscriber task run

    assert starts == 1  # only the first connection started the subscriber
    assert bus.listener_count("sid-multi") == 2

    # Closing one connection leaves the shared subscriber running…
    await s1.aclose()
    assert bus.get_task_subscriber("sid-multi") is not None
    # …closing the last tears it down.
    await s2.aclose()
    assert bus.get_task_subscriber("sid-multi") is None


# --------------------------------------------------------------------------- #
# E-1 — in-flight status history accumulates (deduped, capped)
# --------------------------------------------------------------------------- #


async def test_on_status_accumulates_deduped_history():
    from app.routers.chat import _make_on_status

    bus = EventBus()
    queue = bus.register("sid-1")
    on_status = _make_on_status(bus, "sid-1", "turn-x")
    assert on_status is not None

    await on_status("step one")
    await on_status("step one")  # consecutive duplicate → suppressed, no event
    await on_status("step two")

    first = await queue.get()
    second = await queue.get()
    assert first.history == ["step one"]
    assert second.history == ["step one", "step two"]
    assert queue.empty()


# --------------------------------------------------------------------------- #
# GET /api/events — endpoint wiring & frame shaping
# --------------------------------------------------------------------------- #


def _authed_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app import security
    from app.config import settings
    from app.main import app
    from app.services.events import EventBus
    from app.sessions import SessionStore

    monkeypatch.setattr(settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(security.settings, "jwt_secret", "test-secret", raising=False)

    store = SessionStore()
    store.get_or_create("sid-evt").conversation_id = "c1"
    app.state.session_store = store
    app.state.event_bus = EventBus()
    token = security.issue_token(security.User(identifier="alice"), sid="sid-evt")
    client = TestClient(app)
    client.cookies.set(settings.cookie_name, token)
    return client, app


def test_events_requires_auth(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/events")
    assert resp.status_code == 401


async def test_event_stream_shapes_connect_heartbeat_and_status_frame(monkeypatch):
    """Drive ``_event_stream`` directly: connect comment, then a status frame.

    Avoids ``TestClient.stream`` (which runs the generator on a separate loop, so
    a queue published from the test loop would never be seen). The subscriber is
    stubbed to a no-op so the stream stays alive on real events only.
    """
    from starlette.requests import Request

    from app.routers.events import _event_stream

    async def _empty_subscribe(redis_url, conversation_id):
        return
        yield  # pragma: no cover - marks this an async generator

    async def _no_snapshot(redis_url, conversation_id, task_id):
        return None

    monkeypatch.setattr(task_events, "subscribe", _empty_subscribe)
    monkeypatch.setattr(task_events, "node_snapshot", _no_snapshot)

    bus = EventBus()
    session = _session(sid="sid-evt")

    # Minimal ASGI request that never reports disconnected.
    scope = {"type": "http", "method": "GET", "headers": []}

    async def _receive():
        return {"type": "http.request"}

    request = Request(scope, _receive)

    stream = _event_stream(request, bus, session)
    first = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
    assert first == ": connected\n\n"

    await bus.publish("sid-evt", StatusEvent(turn_id="t1", message="working"))
    frame = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
    assert frame.startswith("event: status\n")
    assert '"message":"working"' in frame
    assert frame.endswith("\n\n")

    await stream.aclose()
