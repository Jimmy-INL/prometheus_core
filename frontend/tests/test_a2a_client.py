"""Tests for frontend A2A response extraction."""

import asyncio
import json
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from utils.a2a_client import A2AClient


class _FakeStreamingResponse:
    def __init__(self, lines, *, content_type="application/x-ndjson"):
        self._lines = lines
        self.headers = {"content-type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def test_parse_response_extracts_conversation_response_from_data_artifact() -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    payload = {
        "conversation_id": "conv-1",
        "status": "completed",
        "message": "SVG artifact created successfully.",
        "new_artifacts": [
            {
                "artifact_id": "artifact-1",
                "conversation_id": "conv-1",
                "name": "prometheus.svg",
                "description": "Debug SVG containing the word 'prometheus'.",
                "uri": "http://localhost:8008/artifacts/conv-1/prometheus.svg",
                "mime_type": "image/svg+xml",
                "metadata": {"word": "prometheus"},
            }
        ],
    }

    result = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "text": json.dumps(payload),
                        }
                    ]
                }
            }
        }
    }

    response = client._parse_response(result)

    assert response.status == "completed"
    assert response.message == "SVG artifact created successfully."
    assert response.new_artifacts is not None
    assert response.new_artifacts[0]["name"] == "prometheus.svg"


def test_parse_response_rejects_pre_v1_rooted_text_part() -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    payload = {
        "conversation_id": "conv-1",
        "status": "needs_info",
        "message": "I need the operating temperature.",
        "followup_questions": [
            {
                "field": "context.temperature_c",
                "question": "Operating temperature in Celsius",
                "type": "number",
            }
        ],
    }

    result = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "root": {
                                "kind": "text",
                                "text": json.dumps(payload),
                            }
                        }
                    ]
                }
            }
        }
    }

    try:
        client._parse_response(result)
    except ValueError as exc:
        assert "unsupported status part fields ['root']" in str(exc)
    else:
        raise AssertionError("pre-v1 rooted part was accepted")


def test_send_streams_sse_statuses_and_final_response(monkeypatch) -> None:
    final_payload = {
        "conversation_id": "conv-1",
        "status": "completed",
        "message": "Done.",
    }
    stream_events = [
        {
            "result": {
                "statusUpdate": {
                    "contextId": "conv-1",
                    "taskId": "task-1",
                    "status": {
                        "state": "TASK_STATE_WORKING",
                        "message": {"parts": [{"text": "Thinking..."}]},
                    },
                }
            }
        },
        {
            "result": {
                "statusUpdate": {
                    "contextId": "conv-1",
                    "taskId": "task-1",
                    "status": {
                        "state": "TASK_STATE_COMPLETED",
                        "message": {"parts": [{"text": json.dumps(final_payload)}]},
                    },
                }
            }
        },
    ]
    sse_lines = []
    for event in stream_events:
        sse_lines.append(f"data: {json.dumps(event)}")
        sse_lines.append("")
    statuses = []
    captured = {}

    async def _on_status(message: str):
        statuses.append(message)

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers", {})
            return _FakeStreamingResponse(sse_lines, content_type="text/event-stream")

    monkeypatch.setattr("utils.a2a_client.httpx.AsyncClient", _FakeAsyncClient)

    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    response = asyncio.run(
        client.send(
            query="hello",
            conversation_id="conv-1",
            on_status=_on_status,
        )
    )

    assert statuses == ["Thinking..."]
    assert captured["method"] == "POST"
    assert captured["url"] == "http://example.test"
    assert captured["json"]["method"] == "SendStreamingMessage"
    # conversationId must travel as the A2A-spec message.contextId so the
    # client-agent's RequestContext.context_id matches the conversation.
    assert captured["json"]["params"]["message"]["contextId"] == "conv-1"
    assert captured["json"]["params"]["message"]["role"] == "ROLE_USER"
    assert captured["json"]["params"]["message"]["parts"] == [
        {"text": json.dumps({"query": "hello", "conversation_id": "conv-1"})}
    ]
    assert captured["json"]["params"]["configuration"] == {"returnImmediately": False}
    assert "application/x-ndjson" in captured["headers"]["Accept"]
    assert captured["headers"]["A2A-Version"] == "1.0"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert response.status == "completed"
    assert response.message == "Done."


def test_send_accepts_ndjson_stream(monkeypatch) -> None:
    final_payload = {
        "conversation_id": "conv-2",
        "status": "answer",
        "message": "NDJSON done.",
    }
    lines = [
        json.dumps(
            {
                "result": {
                    "statusUpdate": {
                        "contextId": "conv-2",
                        "taskId": "task-2",
                        "status": {
                            "state": "TASK_STATE_WORKING",
                            "message": {"parts": [{"text": "Working..."}]},
                        },
                    }
                }
            }
        ),
        json.dumps(
            {
                "result": {
                    "statusUpdate": {
                        "contextId": "conv-2",
                        "taskId": "task-2",
                        "status": {
                            "state": "TASK_STATE_COMPLETED",
                            "message": {"parts": [{"text": json.dumps(final_payload)}]},
                        },
                    }
                }
            }
        ),
    ]
    statuses = []

    async def _on_status(message: str):
        statuses.append(message)

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            return _FakeStreamingResponse(lines, content_type="application/x-ndjson")

    monkeypatch.setattr("utils.a2a_client.httpx.AsyncClient", _FakeAsyncClient)

    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    response = asyncio.run(
        client.send(
            query="hello",
            conversation_id="conv-2",
            on_status=_on_status,
        )
    )

    assert statuses == ["Working..."]
    assert response.status == "answer"
    assert response.message == "NDJSON done."


def test_stage_upload_streams_file_bytes(monkeypatch, tmp_path: Path) -> None:
    upload_path = tmp_path / "mesh.e"
    upload_path.write_bytes(b"exodus bytes")
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "upload_id": "abc123",
                "name": "mesh.e",
                "mime_type": "application/x-exodus",
                "size_bytes": 12,
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, params, headers, content):
            chunks = []
            async for chunk in content:
                chunks.append(chunk)
            captured.update(
                {
                    "url": url,
                    "params": params,
                    "headers": headers,
                    "body": b"".join(chunks),
                }
            )
            return _FakeResponse()

    monkeypatch.setattr("utils.a2a_client.httpx.AsyncClient", _FakeAsyncClient)

    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    result = asyncio.run(
        client.stage_upload(
            upload_path,
            name="mesh.e",
            mime_type="application/x-exodus",
            conversation_id="conv-1",
        )
    )

    assert result["upload_id"] == "abc123"
    assert captured["url"] == "http://example.test/uploads/stage"
    assert captured["params"]["conversation_id"] == "conv-1"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["Content-Length"] == "12"
    assert captured["body"] == b"exodus bytes"
