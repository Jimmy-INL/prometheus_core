"""Tests for components/message_handler.py."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from components import message_handler as handler


def _install_message_spy(monkeypatch):
    sent_messages = []

    class DummyMessage:
        def __init__(self, content="", elements=None):
            self.content = content
            self.elements = elements
            sent_messages.append(self)

        async def send(self):
            return self

        async def remove(self):
            return self

    monkeypatch.setattr(handler.cl, "Message", DummyMessage)
    return sent_messages


@pytest.mark.asyncio
async def test_message_handler_exodus_upload_sends_messages(monkeypatch):
    sent_messages = _install_message_spy(monkeypatch)
    dataset = SimpleNamespace(
        metadata={
            "num_timesteps": 2,
            "num_nodes": 10,
            "num_elements": 5,
            "nodal_variables": [],
            "element_variables": [],
        },
        to_chainlit_element=lambda: "viewer",
    )
    process_exodus = AsyncMock(return_value=dataset)
    monkeypatch.setattr(handler, "process_exodus_upload", process_exodus)

    message = SimpleNamespace(
        content="",
        elements=[SimpleNamespace(name="model.exo", path="/tmp/model.exo")],
    )

    await handler.message_handler(message)

    process_exodus.assert_awaited_once_with(Path("/tmp/model.exo"))
    assert any("Processing Exodus file" in msg.content for msg in sent_messages)
    assert any("Exodus File Loaded" in msg.content for msg in sent_messages)


@pytest.mark.asyncio
async def test_message_handler_ifc_upload_sends_messages(monkeypatch):
    sent_messages = _install_message_spy(monkeypatch)
    dataset = SimpleNamespace(
        file_size=1024,
        to_chainlit_element=lambda: "viewer",
    )
    process_ifc = AsyncMock(return_value=dataset)
    monkeypatch.setattr(handler, "process_ifc_upload", process_ifc)
    monkeypatch.setattr(handler, "format_file_size", lambda size: "1.0 KB")

    message = SimpleNamespace(
        content="",
        elements=[SimpleNamespace(name="model.ifc", path="/tmp/model.ifc")],
    )

    await handler.message_handler(message)

    process_ifc.assert_awaited_once_with(Path("/tmp/model.ifc"))
    assert any("Processing IFC file" in msg.content for msg in sent_messages)
    assert any("IFC File Loaded" in msg.content for msg in sent_messages)


@pytest.mark.asyncio
async def test_message_handler_text_message_routes_to_backend(monkeypatch):
    sent_messages = _install_message_spy(monkeypatch)
    response = MagicMock()
    response.json.return_value = {"response": "hi"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(handler.requests, "post", post)
    monkeypatch.setattr(handler, "settings", SimpleNamespace(platform_url="http://backend"))

    message = SimpleNamespace(content="hello", elements=[])

    await handler.message_handler(message)

    post.assert_called_once_with(
        "http://backend/api/chat",
        json={"message": "hello", "user_id": "user_123", "context": {}, "files": []},
    )
    assert any(msg.content == "Received: hi" for msg in sent_messages)


@pytest.mark.asyncio
async def test_message_handler_workflow_calls_runner(monkeypatch):
    _install_message_spy(monkeypatch)
    response = MagicMock()
    response.json.return_value = {"type": "workflow", "session_id": "sess-123"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(handler.requests, "post", post)
    monkeypatch.setattr(handler, "settings", SimpleNamespace(platform_url="http://backend"))
    runner = AsyncMock()
    monkeypatch.setattr(handler, "_run_demo_workflow", runner)

    message = SimpleNamespace(content="run", elements=[])

    await handler.message_handler(message)

    runner.assert_awaited_once_with("run", "sess-123")
