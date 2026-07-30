"""Tests for follow-up form submission handling."""

from __future__ import annotations

import sys
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

FRONTEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components import message_handler as handler
from utils.a2a_client import ConversationResponse


def test_handle_needs_info_submits_followup_answers(monkeypatch):
    sent_messages = []
    custom_elements = []

    class DummyMessage:
        def __init__(self, content="", elements=None):
            self.content = content
            self.elements = elements
            sent_messages.append(self)

        async def send(self):
            return self

    class DummyCustomElement:
        def __init__(self, name, display=None, props=None):
            self.name = name
            self.display = display
            self.props = props
            custom_elements.append(self)

    class DummyAskElementMessage:
        def __init__(self, content, element, timeout=0, raise_on_timeout=False):
            self.content = content
            self.element = element
            self.timeout = timeout
            self.raise_on_timeout = raise_on_timeout

        async def send(self):
            return {
                "submitted": True,
                "hole_diameter": "0.1",
                "rod_diameter": "0.08",
            }

    class DummyUserSession:
        def __init__(self):
            self._store = {"artifacts": []}

        def get(self, key, default=None):
            return self._store.get(key, default)

        def set(self, key, value):
            self._store[key] = value

    class DummyStep:
        def __init__(self, name="", type="tool"):
            self.name = name
            self.type = type
            self.output = ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def update(self):
            return None

    next_response = ConversationResponse(
        conversation_id="conv-1",
        status="completed",
        message="done",
        report="done",
    )
    client = SimpleNamespace(send=AsyncMock(return_value=next_response))
    handle_response = AsyncMock()

    monkeypatch.setattr(handler.cl, "Message", DummyMessage)
    monkeypatch.setattr(handler.cl, "CustomElement", DummyCustomElement)
    monkeypatch.setattr(handler.cl, "AskElementMessage", DummyAskElementMessage)
    monkeypatch.setattr(handler.cl, "Step", DummyStep)
    monkeypatch.setattr(handler.cl, "user_session", DummyUserSession())
    monkeypatch.setattr(handler, "_handle_response", handle_response)

    response = ConversationResponse(
        conversation_id="conv-1",
        status="needs_info",
        message="Butterfly valve dimensions required",
        followup_questions=[
            {
                "field": "hole_diameter",
                "question": "Hole diameter (m)",
                "type": "number",
                "options": None,
            },
            {
                "field": "rod_diameter",
                "question": "Rod diameter (m)",
                "type": "number",
                "options": None,
            },
        ],
    )

    asyncio.run(
        handler._handle_needs_info(
            client,
            response,
            "Create a butterfly valve",
            "conv-1",
        )
    )

    assert custom_elements[0].props["title"] == "Butterfly valve dimensions required"
    assert [field["label"] for field in custom_elements[0].props["fields"]] == [
        "Hole diameter (m)",
        "Rod diameter (m)",
    ]
    client.send.assert_awaited_once_with(
        query="Create a butterfly valve",
        conversation_id="conv-1",
        followup_answers={
            "hole_diameter": "0.1",
            "rod_diameter": "0.08",
        },
        artifacts=[],
        on_status=client.send.await_args.kwargs["on_status"],
    )
    assert callable(client.send.await_args.kwargs["on_status"])
    handle_response.assert_awaited_once_with(
        client,
        next_response,
        "Create a butterfly valve",
        "conv-1",
        _depth=1,
    )
