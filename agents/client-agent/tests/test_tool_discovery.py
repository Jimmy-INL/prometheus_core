"""Tests for A2A response normalization in tool discovery."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
import types

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))
PROMETHEUS_API_DIR = Path(__file__).resolve().parents[3] / "prometheus_api"
if str(PROMETHEUS_API_DIR) not in sys.path:
    sys.path.insert(0, str(PROMETHEUS_API_DIR))

if "langchain_core.tools" not in sys.modules:
    tools_module = types.ModuleType("langchain_core.tools")

    class _StructuredTool:
        @staticmethod
        def from_function(*args, **kwargs):
            return None

    tools_module.StructuredTool = _StructuredTool
    sys.modules["langchain_core.tools"] = tools_module

import tool_discovery


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, payload, **kwargs):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, endpoint, json=None, headers=None):
        return _FakeResponse(self._payload)


def test_call_a2a_agent_enriches_response_with_native_artifacts(monkeypatch) -> None:
    a2a_payload = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps(
                                {
                                    "status": "completed",
                                    "message": "Artifacts ready.",
                                }
                            ),
                        }
                    ]
                }
            },
            "artifacts": [
                {
                    "artifactId": "artifact-file",
                    "name": "mesh.exo",
                    "description": "Mesh output",
                    "parts": [
                        {
                            "kind": "file",
                            "file": {
                                "uri": "deeplynx://container/file/mesh-123",
                                "mimeType": "application/octet-stream",
                                "name": "mesh.exo",
                            },
                        }
                    ],
                    "metadata": {
                        "conversation_id": "conv-1",
                        "producer_agent_id": "artifact-debug-agent",
                    },
                },
                {
                    "artifactId": "artifact-message",
                    "name": "conversation_message",
                    "parts": [
                        {
                            "kind": "data",
                            "data": {"message": "SVG artifact created successfully."},
                            "metadata": {
                                "mime_type": "application/json",
                                "kind": "conversation_message",
                            },
                        }
                    ],
                    "metadata": {
                        "conversation_id": "conv-1",
                        "producer_agent_id": "artifact-debug-agent",
                    },
                },
                {
                    "artifactId": "artifact-json",
                    "name": "Corrosion Summary",
                    "parts": [
                        {
                            "kind": "data",
                            "data": {"material_id": "Alloy 600", "finding_count": 3},
                            "metadata": {
                                "mime_type": "application/json",
                                "json_type": "prometheus.analysis.corrosion_summary.v1",
                            },
                        }
                    ],
                    "metadata": {
                        "conversation_id": "conv-1",
                        "producer_agent_id": "analysis-agent",
                    },
                },
            ],
        }
    }

    monkeypatch.setattr(
        tool_discovery.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(payload=a2a_payload, **kwargs),
    )

    result = asyncio.run(
        tool_discovery.call_a2a_agent(
            "http://example.test/a2a/artifact-debug-agent",
            "create_json_artifact",
            conversation_id="conv-1",
        )
    )

    assert result["status"] == "completed"
    assert len(result["artifacts"]) == 2
    assert [artifact["name"] for artifact in result["artifacts"]] == [
        "mesh.exo",
        "Corrosion Summary",
    ]
    assert result["artifacts"][0]["uri"] == "deeplynx://container/file/mesh-123"
    assert result["artifacts"][1]["json_type"] == "prometheus.analysis.corrosion_summary.v1"
    assert result["artifacts"][1]["json_body"] == {
        "material_id": "Alloy 600",
        "finding_count": 3,
    }
