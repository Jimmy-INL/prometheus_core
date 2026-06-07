"""Tests for frontend background-task handling (backgrounded status + watcher)."""

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


# --- backgrounded branch -----------------------------------------------------


class _DummyMessage:
    sent: list = []

    def __init__(self, content="", elements=None):
        self.content = content
        self.elements = elements
        _DummyMessage.sent.append(self)

    async def send(self):
        return self


def test_handle_backgrounded_acks_and_spawns_watcher(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)

    spawned = {}

    def fake_create_task(coro):
        spawned["coro"] = coro
        coro.close()  # don't actually run the watcher in this test
        return None

    monkeypatch.setattr(handler.asyncio, "create_task", fake_create_task)

    resp = ConversationResponse(
        conversation_id="c1",
        status="backgrounded",
        message="running in background",
        message_metadata={"task_id": "root-1"},
    )
    asyncio.run(handler._handle_backgrounded(resp, "c1"))

    assert _DummyMessage.sent and "background" in _DummyMessage.sent[0].content
    assert "coro" in spawned  # watcher was scheduled


def test_handle_backgrounded_without_task_id_does_not_spawn(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)

    spawned = {"called": False}

    def fake_create_task(coro):
        spawned["called"] = True
        coro.close()
        return None

    monkeypatch.setattr(handler.asyncio, "create_task", fake_create_task)

    resp = ConversationResponse(conversation_id="c1", status="backgrounded", message="x")
    asyncio.run(handler._handle_backgrounded(resp, "c1"))

    assert spawned["called"] is False


# --- watcher: completion path ------------------------------------------------


def test_watcher_renders_result_on_completion(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)

    async def fake_wait(redis_url, conv, task_id):
        return "completed"

    async def fake_fetch(redis_url, conv, task_id):
        return {"conversation_id": conv, "status": "completed", "report": "the answer"}

    rendered = {}

    async def fake_final(response):
        rendered["response"] = response

    monkeypatch.setattr(task_events, "wait_for_task", fake_wait)
    monkeypatch.setattr(task_events, "fetch_result", fake_fetch)
    monkeypatch.setattr(handler, "_handle_final_response", fake_final)

    asyncio.run(handler._watch_background_task("c1", "root-1"))

    assert rendered["response"].report == "the answer"
    assert any("complete" in m.content for m in _DummyMessage.sent)


def test_watcher_reports_non_completed_state(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)

    async def fake_wait(redis_url, conv, task_id):
        return "failed"

    called = {"final": False, "fetch": False}

    async def fake_fetch(*a, **k):
        called["fetch"] = True
        return None

    async def fake_final(response):
        called["final"] = True

    monkeypatch.setattr(task_events, "wait_for_task", fake_wait)
    monkeypatch.setattr(task_events, "fetch_result", fake_fetch)
    monkeypatch.setattr(handler, "_handle_final_response", fake_final)

    asyncio.run(handler._watch_background_task("c1", "root-1"))

    assert called["final"] is False
    assert any("failed" in m.content for m in _DummyMessage.sent)


def test_watcher_noop_when_redis_unavailable(monkeypatch):
    _DummyMessage.sent = []
    monkeypatch.setattr(handler.cl, "Message", _DummyMessage)

    async def fake_wait(redis_url, conv, task_id):
        return None

    monkeypatch.setattr(task_events, "wait_for_task", fake_wait)
    asyncio.run(handler._watch_background_task("c1", "root-1"))

    assert _DummyMessage.sent == []
