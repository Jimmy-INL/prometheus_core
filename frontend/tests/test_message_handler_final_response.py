"""Tests for final response rendering."""

from __future__ import annotations

import asyncio
import json
import sys

FRONTEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components import message_handler as handler
from utils.a2a_client import ConversationResponse


class DummyUserSession:
    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


def _install_message_spy(monkeypatch):
    sent_messages = []

    class DummyMessage:
        def __init__(self, content="", elements=None):
            self.content = content
            self.elements = elements
            sent_messages.append(self)

        async def send(self):
            return self

    session = DummyUserSession()
    monkeypatch.setattr(handler.cl, "Message", DummyMessage)
    monkeypatch.setattr(handler.cl, "user_session", session)
    return sent_messages, session


def test_handle_final_response_renders_only_new_artifact_delta(monkeypatch):
    sent_messages, session = _install_message_spy(monkeypatch)
    rendered_artifacts = []

    async def _fake_render_artifacts(artifacts, tmp_dir):
        rendered_artifacts.extend(artifacts)
        return ["viewer"], "Artifact text"

    monkeypatch.setattr(handler, "render_artifacts", _fake_render_artifacts)

    response = ConversationResponse(
        conversation_id="conv-1",
        status="completed",
        message=json.dumps(
            {
                "status": "success",
                "agent": "Alchemy Agent",
                "final_step": "completed",
            }
        ),
        artifacts=[
            {
                "artifact_id": "old-model",
                "name": "old-model.ifc",
                "mime_type": "application/ifc",
            },
            {
                "artifact_id": "new-model",
                "name": "new-model.ifc",
                "mime_type": "application/ifc",
            },
        ],
        new_artifacts=[
            {
                "artifact_id": "new-model",
                "name": "new-model.ifc",
                "mime_type": "application/ifc",
            }
        ],
    )

    asyncio.run(handler._handle_final_response(response))

    assert session.get("artifacts") == response.artifacts
    assert [artifact["artifact_id"] for artifact in rendered_artifacts] == ["new-model"]
    assert len(sent_messages) == 1
    assert sent_messages[0].elements == ["viewer"]
    assert '"agent": "Alchemy Agent"' in sent_messages[0].content
    assert "Artifact text" in sent_messages[0].content


def test_handle_final_response_does_not_render_catalog_when_delta_is_empty(monkeypatch):
    sent_messages, session = _install_message_spy(monkeypatch)

    async def _should_not_render_artifacts(artifacts, tmp_dir):
        raise AssertionError("The full conversation catalog must not be rendered.")

    monkeypatch.setattr(handler, "render_artifacts", _should_not_render_artifacts)

    response = ConversationResponse(
        conversation_id="conv-1",
        status="completed",
        message="No new artifact was created.",
        artifacts=[
            {
                "artifact_id": "old-model",
                "name": "old-model.ifc",
                "mime_type": "application/ifc",
            }
        ],
        new_artifacts=[],
    )

    asyncio.run(handler._handle_final_response(response))

    assert session.get("artifacts") == response.artifacts
    assert len(sent_messages) == 1
    assert sent_messages[0].elements == []
    assert sent_messages[0].content == "No new artifact was created."


def test_handle_final_response_does_not_repeat_user_upload_viewer(monkeypatch):
    sent_messages, _session = _install_message_spy(monkeypatch)
    rendered_artifacts = []

    async def _fake_render_artifacts(artifacts, tmp_dir):
        rendered_artifacts.extend(artifacts)
        return ["viewer"], ""

    uploaded = {
        "artifact_id": "uploaded-model",
        "name": "attached.ifc",
        "mime_type": "application/ifc",
        "metadata": {"source": "user-upload"},
    }
    generated = {
        "artifact_id": "generated-report",
        "name": "report.json",
        "mime_type": "application/json",
    }

    monkeypatch.setattr(handler, "render_artifacts", _fake_render_artifacts)

    response = ConversationResponse(
        conversation_id="conv-1",
        status="completed",
        message="Here is the attached artifact and generated report.",
        artifacts=[uploaded, generated],
        new_artifacts=[uploaded, generated],
    )

    asyncio.run(handler._handle_final_response(response))

    assert [artifact["artifact_id"] for artifact in rendered_artifacts] == [
        "generated-report"
    ]
    assert sent_messages[0].elements == ["viewer"]


def test_handle_final_response_does_not_render_artifacts_for_slash_commands(monkeypatch):
    sent_messages, session = _install_message_spy(monkeypatch)

    async def _should_not_render_artifacts(artifacts, tmp_dir):
        raise AssertionError("Slash-command artifact catalogs should be listed, not rendered.")

    monkeypatch.setattr(handler, "render_artifacts", _should_not_render_artifacts)

    response = ConversationResponse(
        conversation_id="conv-1",
        status="answer",
        message="Conversation artifacts (1)\n- tiger.svg",
        artifacts=[{"artifact_id": "svg-1", "name": "tiger.svg"}],
        message_metadata={"slash_command": "artifacts"},
    )

    asyncio.run(handler._handle_final_response(response))

    assert session.get("artifacts") == response.artifacts
    assert len(sent_messages) == 1
    assert sent_messages[0].elements == []
    assert sent_messages[0].content == "Conversation artifacts (1)\n- tiger.svg"
