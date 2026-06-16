"""Tests for frontend background-task handling: the backgrounded ack, the
per-session notifier, and the idempotent completion announce."""

from __future__ import annotations

import asyncio
import sys

FRONTEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components import message_handler as handler
from utils import task_events
from utils.a2a_client import ConversationResponse, response_from_payload


# --- pure helpers ------------------------------------------------------------


def test_is_terminal():
    assert task_events.is_terminal("completed")
    assert task_events.is_terminal("failed")
    assert task_events.is_terminal("canceled")
    assert task_events.is_terminal("rejected")
    assert not task_events.is_terminal("working")
    assert not task_events.is_terminal(None)


def test_event_and_key_names():
    assert task_events.events_channel("c1") == "tasks:events:c1"
    assert task_events._result_key("c1", "t1") == "tasks:result:c1:t1"
    assert task_events._node_key("c1", "t1") == "tasks:node:c1:t1"


def test_response_from_payload_roundtrips_fields():
    resp = response_from_payload(
        {
            "conversation_id": "c1",
            "status": "completed",
            "report": "done",
            "new_artifacts": [{"artifact_id": "a1"}],
            "message_metadata": {"k": "v"},
        }
    )
    assert isinstance(resp, ConversationResponse)
    assert resp.status == "completed"
    assert resp.report == "done"
    assert resp.new_artifacts == [{"artifact_id": "a1"}]
    assert resp.message_metadata == {"k": "v"}


# --- test doubles ------------------------------------------------------------


class _DummyMessage:
    sent: list = []

    def __init__(self, content="", elements=None):
        self.content = content
        self.elements = elements
        _DummyMessage.sent.append(self)

    async def send(self):
        return self


class _FakeUserSession:
    def __init__(self):
        self._d: dict = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value):
        self._d[key] = value


def _install_doubles(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)
    monkeypatch.setattr(handler.cl, "user_session", _FakeUserSession())


# --- _handle_backgrounded ----------------------------------------------------


def test_handle_backgrounded_acks_and_registers_id(monkeypatch):
    _install_doubles(monkeypatch)

    async def not_terminal(*a, **k):
        return "working"

    monkeypatch.setattr(task_events, "node_state", not_terminal)

    resp = ConversationResponse(
        conversation_id="c1",
        status="backgrounded",
        message="running in background",
        message_metadata={"task_id": "root-1"},
    )
    asyncio.run(handler._handle_backgrounded(resp, "c1"))

    assert _DummyMessage.sent and "background" in _DummyMessage.sent[0].content
    assert handler._awaited_task_ids() == {"root-1"}  # registered for the notifier


def test_handle_backgrounded_without_task_id_registers_nothing(monkeypatch):
    _install_doubles(monkeypatch)
    resp = ConversationResponse(conversation_id="c1", status="backgrounded", message="x")
    asyncio.run(handler._handle_backgrounded(resp, "c1"))
    assert handler._awaited_task_ids() == set()


def test_handle_backgrounded_fast_finish_announces_immediately(monkeypatch):
    """If the task already finished before the notifier saw an event, the
    fast-finish guard announces right away."""
    _install_doubles(monkeypatch)

    async def already_done(*a, **k):
        return "completed"

    async def fake_fetch(*a, **k):
        return {"conversation_id": "c1", "status": "completed", "report": "fast"}

    rendered = {}

    async def fake_final(response):
        rendered["report"] = response.report

    monkeypatch.setattr(task_events, "node_state", already_done)
    monkeypatch.setattr(task_events, "fetch_result", fake_fetch)
    monkeypatch.setattr(handler, "_handle_final_response", fake_final)

    resp = ConversationResponse(
        conversation_id="c1", status="backgrounded", message="x", message_metadata={"task_id": "root-1"}
    )
    asyncio.run(handler._handle_backgrounded(resp, "c1"))

    assert rendered.get("report") == "fast"
    assert handler._awaited_task_ids() == set()  # consumed, won't double-announce


# --- _maybe_announce_completion ----------------------------------------------


def test_announce_renders_result_and_is_idempotent(monkeypatch):
    _install_doubles(monkeypatch)
    handler.cl.user_session.set(handler.BACKGROUNDED_IDS_KEY, {"root-1"})

    async def fake_fetch(*a, **k):
        return {"conversation_id": "c1", "status": "completed", "report": "the answer"}

    calls = {"final": 0}

    async def fake_final(response):
        calls["final"] += 1

    monkeypatch.setattr(task_events, "fetch_result", fake_fetch)
    monkeypatch.setattr(handler, "_handle_final_response", fake_final)

    asyncio.run(handler._maybe_announce_completion("c1", "root-1", "completed"))
    assert calls["final"] == 1
    assert any("complete" in m.content for m in _DummyMessage.sent)

    # Second call for the same id is a no-op (id already consumed).
    asyncio.run(handler._maybe_announce_completion("c1", "root-1", "completed"))
    assert calls["final"] == 1


def test_announce_reports_non_completed_state(monkeypatch):
    _install_doubles(monkeypatch)
    handler.cl.user_session.set(handler.BACKGROUNDED_IDS_KEY, {"root-1"})

    called = {"final": False}

    async def fake_final(response):
        called["final"] = True

    monkeypatch.setattr(handler, "_handle_final_response", fake_final)
    asyncio.run(handler._maybe_announce_completion("c1", "root-1", "failed"))

    assert called["final"] is False
    assert any("failed" in m.content for m in _DummyMessage.sent)


def test_announce_skips_unawaited_id(monkeypatch):
    _install_doubles(monkeypatch)  # empty awaited set
    asyncio.run(handler._maybe_announce_completion("c1", "ghost", "completed"))
    assert _DummyMessage.sent == []


# --- run_task_notifier -------------------------------------------------------


def test_notifier_announces_awaited_terminal_event(monkeypatch):
    _install_doubles(monkeypatch)
    handler.cl.user_session.set(handler.BACKGROUNDED_IDS_KEY, {"root-1"})

    async def fake_subscribe(redis_url, conv):
        # an internal sub-node (ignored), then the awaited root completing
        yield {"type": "node-completed", "task_id": "child-9", "state": "completed"}
        yield {"type": "node-updated", "task_id": "root-1", "state": "working"}
        yield {"type": "node-completed", "task_id": "root-1", "state": "completed"}

    async def fake_fetch(*a, **k):
        return {"conversation_id": "c1", "status": "completed", "report": "done"}

    rendered = {}

    async def fake_final(response):
        rendered["report"] = response.report

    monkeypatch.setattr(task_events, "subscribe", fake_subscribe)
    monkeypatch.setattr(task_events, "fetch_result", fake_fetch)
    monkeypatch.setattr(handler, "_handle_final_response", fake_final)

    asyncio.run(handler.run_task_notifier(object(), "c1"))

    assert rendered.get("report") == "done"
    assert handler._awaited_task_ids() == set()  # root-1 consumed; child-9 never awaited


def test_notifier_noop_when_no_events(monkeypatch):
    _install_doubles(monkeypatch)

    async def empty_subscribe(redis_url, conv):
        return
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(task_events, "subscribe", empty_subscribe)
    asyncio.run(handler.run_task_notifier(object(), "c1"))
    assert _DummyMessage.sent == []
