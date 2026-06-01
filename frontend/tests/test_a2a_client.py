"""Tests for frontend A2A response extraction."""

import asyncio
import json
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from utils.a2a_client import A2AClient


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
                            "kind": "text",
                            "text": json.dumps(payload),
                        }
                    ]
                }
            }
        }
    }

    response = client._parse_response(result, "fallback-conv")

    assert response.status == "completed"
    assert response.message == "SVG artifact created successfully."
    assert response.new_artifacts is not None
    assert response.new_artifacts[0]["name"] == "prometheus.svg"


def test_parse_response_extracts_from_rooted_text_part() -> None:
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

    response = client._parse_response(result, "fallback-conv")

    assert response.status == "needs_info"
    assert response.followup_questions is not None
    assert response.followup_questions[0]["field"] == "context.temperature_c"


def test_poll_status_starts_after_existing_history(monkeypatch) -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    seen = []

    class _FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def json(self):
            return self._payload

    class _DoneTask:
        def __init__(self):
            self._done = False

        def done(self):
            return self._done

        def mark_done(self):
            self._done = True

    status_calls = [
        {
            "history": [
                {"message": "old-1"},
                {"message": "old-2"},
            ]
        },
        {
            "history": [
                {"message": "old-1"},
                {"message": "old-2"},
                {"message": "new-1"},
                {"message": "new-2"},
            ]
        },
    ]

    async def _fake_sleep(_seconds):
        return None

    async def _fake_on_status(message: str):
        seen.append(message)
        if len(seen) >= 2:
            send_task.mark_done()

    send_task = _DoneTask()

    monkeypatch.setattr("utils.a2a_client.asyncio.sleep", _fake_sleep)

    class _Client:
        async def get(self, url, headers=None, timeout=None):
            return _FakeResponse(status_calls.pop(0))

    async def _run():
        fake_client = _Client()
        history_count = await client._get_status_history_count(
            fake_client,
            "conv-1",
            {},
        )
        await client._poll_status(
            fake_client,
            "conv-1",
            {},
            _fake_on_status,
            send_task,
            initial_seen_count=history_count,
        )

    asyncio.run(_run())

    assert seen == ["new-1", "new-2"]


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
