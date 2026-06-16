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

if "prometheus_api.agent" not in sys.modules:
    prometheus_api_module = types.ModuleType("prometheus_api")
    agent_module = types.ModuleType("prometheus_api.agent")

    class _ArtifactReference:
        def __init__(
            self,
            *,
            artifact_id: str | None = None,
            conversation_id: str | None = None,
            name: str | None = None,
            description: str | None = None,
            uri: str | None = None,
            metadata: dict | None = None,
            json_type: str | None = None,
            json_body: dict | None = None,
        ):
            self.artifact_id = artifact_id
            self.conversation_id = conversation_id
            self.name = name
            self.description = description
            self.uri = uri
            self.metadata = metadata or {}
            self.json_type = json_type
            self.json_body = json_body

        @classmethod
        def from_any(cls, artifact, conversation_id=None):
            if not isinstance(artifact, dict):
                return None

            name = artifact.get("name")
            description = artifact.get("description")
            metadata = dict(artifact.get("metadata") or {})
            parts = artifact.get("parts") or []
            uri = None
            json_type = None
            json_body = None

            for part in parts:
                if not isinstance(part, dict):
                    continue
                kind = str(part.get("kind") or "").strip().lower()
                if kind == "file":
                    file_payload = part.get("file") or {}
                    uri = file_payload.get("uri")
                elif kind == "data":
                    json_body = part.get("data")
                    part_meta = dict(part.get("metadata") or {})
                    json_type = part_meta.get("json_type")
                    metadata = {**part_meta, **metadata}

            return cls(
                artifact_id=artifact.get("artifactId") or artifact.get("artifact_id"),
                conversation_id=conversation_id or metadata.get("conversation_id"),
                name=name,
                description=description,
                uri=uri,
                metadata=metadata,
                json_type=json_type,
                json_body=json_body,
            )

        def to_dict(self):
            payload = {
                "artifact_id": self.artifact_id,
                "conversation_id": self.conversation_id,
                "name": self.name,
                "description": self.description,
                "uri": self.uri,
                "metadata": self.metadata,
            }
            if self.json_type is not None:
                payload["json_type"] = self.json_type
            if self.json_body is not None:
                payload["json_body"] = self.json_body
            return payload

    agent_module.ArtifactReference = _ArtifactReference

    class _PrometheusAgent:
        def __init__(self, *args, **kwargs):
            self.artifact_registry = types.SimpleNamespace(register=lambda reference: None)

        @staticmethod
        def registry_url() -> str:
            return "http://litellm:4000"

        @staticmethod
        def pending_hint(pending_requests, hint):
            return hint

        def list_artifact_references(self, *args, **kwargs):
            return []

        async def send_status_update(self, *args, **kwargs):
            return None

    agent_module.EventQueue = object
    agent_module.PrometheusAgent = _PrometheusAgent
    agent_module.RequestContext = object
    prometheus_api_module.agent = agent_module
    sys.modules["prometheus_api"] = prometheus_api_module
    sys.modules["prometheus_api.agent"] = agent_module

import tool_discovery


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

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


class _FakeSSE:
    def __init__(self, data):
        self.data = data


class _FakeEventSource:
    def __init__(self, events, status_code=200):
        self._events = events
        self.response = _FakeResponse({}, status_code=status_code)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def aiter_sse(self):
        for event in self._events:
            yield _FakeSSE(event)


class _FakeStreamingResponse:
    def __init__(self, lines, *, content_type="application/x-ndjson", status_code=200):
        self._lines = lines
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def test_get_agent_card_prefers_raw_prometheus_endpoint(monkeypatch) -> None:
    responses = {
        "http://thermal-agent:8000/api/agent-card": _FakeResponse(
            {
                "skills": [
                    {
                        "id": "analyze_thermal",
                        "inputSchema": {
                            "type": "object",
                            "required": ["material_id", "context"],
                        },
                        "requires_approval": True,
                    }
                ]
            }
        )
    }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, endpoint):
            return responses.get(endpoint, _FakeResponse({}, status_code=404))

    monkeypatch.setattr(tool_discovery.httpx, "AsyncClient", _Client)

    result = asyncio.run(
        tool_discovery.get_agent_card(
            "thermal-analysis-agent",
            direct_url="http://thermal-agent:8000",
        )
    )

    assert result["skills"][0]["requires_approval"] is True
    assert result["skills"][0]["inputSchema"]["required"] == ["material_id", "context"]


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


def test_call_a2a_agent_preserves_error_payload_from_final_status(monkeypatch) -> None:
    a2a_payload = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps(
                                {
                                    "error": "context.temperature_c is required",
                                }
                            ),
                        }
                    ]
                }
            }
        }
    }

    monkeypatch.setattr(
        tool_discovery.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(payload=a2a_payload, **kwargs),
    )

    result = asyncio.run(
        tool_discovery.call_a2a_agent(
            "http://example.test/a2a/thermal-analysis-agent",
            "analyze_thermal",
            conversation_id="conv-1",
            material_id="SS316",
        )
    )

    assert result == {"error": "context.temperature_c is required"}


def test_get_all_tools_dynamic_fetches_full_agent_card(monkeypatch) -> None:
    async def fake_discover_agents():
        return [
            {
                "agent_id": "thermal-analysis-agent",
                "name": "Thermal Analysis Agent",
                "url": "http://thermal-agent:8000",
                "agent_card_params": {"skills": []},
            }
        ]

    async def fake_get_agent_card(agent_id: str, direct_url: str | None = None):
        assert agent_id == "thermal-analysis-agent"
        assert direct_url == "http://thermal-agent:8000"
        return {
            "capabilities": {"streaming": True},
            "skills": [
                {
                    "id": "analyze_thermal",
                    "description": "Analyze thermal effects",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "material_id": {"type": "string"},
                            "context": {
                                "type": "object",
                                "properties": {
                                    "temperature_c": {"type": "number"},
                                },
                                "required": ["temperature_c"],
                            },
                        },
                        "required": ["material_id", "context"],
                    },
                }
            ]
        }

    created = []

    async def fake_create_tool_from_skill(
        agent_url: str,
        skill: dict,
        supports_streaming: bool = False,
    ):
        created.append((agent_url, skill, supports_streaming))
        return {"agent_url": agent_url, "skill": skill["id"]}

    monkeypatch.setattr(tool_discovery, "discover_agents", fake_discover_agents)
    monkeypatch.setattr(tool_discovery, "get_agent_card", fake_get_agent_card)
    monkeypatch.setattr(tool_discovery, "create_tool_from_skill", fake_create_tool_from_skill)

    tools = asyncio.run(tool_discovery.get_all_tools_dynamic())

    assert tools == [
        {
            "agent_url": "http://litellm:4000/a2a/thermal-analysis-agent",
            "skill": "analyze_thermal",
        }
    ]
    assert created[0][1]["inputSchema"]["properties"]["context"]["required"] == ["temperature_c"]
    assert created[0][2] is True


def test_call_a2a_agent_streaming_parses_final_status_and_artifacts(monkeypatch) -> None:
    streamed_events = [
        json.dumps(
            {
                "result": {
                    "kind": "status-update",
                    "contextId": "conv-1",
                    "taskId": "task-1",
                    "final": False,
                    "status": {
                        "state": "working",
                        "message": {
                            "parts": [
                                {
                                    "kind": "text",
                                    "text": "Searching publications...",
                                }
                            ]
                        },
                    },
                }
            }
        ),
        json.dumps(
            {
                "result": {
                    "kind": "artifact-update",
                    "contextId": "conv-1",
                    "taskId": "task-1",
                    "artifact": {
                        "artifactId": "artifact-1",
                        "name": "paper-summary.json",
                        "parts": [
                            {
                                "kind": "data",
                                "data": {"count": 4},
                                "metadata": {
                                    "mime_type": "application/json",
                                    "json_type": "prometheus.analysis.summary.v1",
                                },
                            }
                        ],
                        "metadata": {
                            "conversation_id": "conv-1",
                            "producer_agent_id": "osti-research-agent",
                        },
                    },
                }
            }
        ),
        json.dumps(
            {
                "result": {
                    "kind": "status-update",
                    "contextId": "conv-1",
                    "taskId": "task-1",
                    "final": True,
                    "status": {
                        "state": "completed",
                        "message": {
                            "parts": [
                                {
                                    "kind": "text",
                                    "text": json.dumps(
                                        {
                                            "status": "completed",
                                            "message": "Research complete.",
                                        }
                                    ),
                                }
                            ]
                        },
                    },
                }
            }
        ),
    ]

    statuses = []
    request_capture = {}

    async def _status_callback(message: str) -> None:
        statuses.append(message)

    class _StreamingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            request_capture["method"] = method
            request_capture["url"] = url
            request_capture["json"] = kwargs.get("json")
            request_capture["headers"] = kwargs.get("headers", {})
            sse_lines = []
            for event in streamed_events:
                sse_lines.append(f"data: {event}")
                sse_lines.append("")
            return _FakeStreamingResponse(sse_lines, content_type="text/event-stream")

    monkeypatch.setattr(tool_discovery.httpx, "AsyncClient", _StreamingClient)

    result = asyncio.run(
        tool_discovery.call_a2a_agent(
            "http://example.test/a2a/osti-research-agent",
            "search_literature",
            conversation_id="conv-1",
            question="What is the creep rate of SS316?",
            _prefer_streaming=True,
            _status_callback=_status_callback,
        )
    )

    assert statuses == ["Searching publications..."]
    assert request_capture["method"] == "POST"
    assert request_capture["url"] == "http://example.test/a2a/osti-research-agent"
    assert request_capture["json"]["method"] == "message/stream"
    assert "application/x-ndjson" in request_capture["headers"]["Accept"]
    assert result["status"] == "completed"
    assert result["message"] == "Research complete."
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["name"] == "paper-summary.json"


def test_call_a2a_agent_streaming_accepts_ndjson(monkeypatch) -> None:
    streamed_lines = [
        json.dumps(
            {
                "result": {
                    "kind": "status-update",
                    "contextId": "conv-2",
                    "taskId": "task-2",
                    "final": False,
                    "status": {
                        "state": "working",
                        "message": {
                            "parts": [{"kind": "text", "text": "Rendering SVG..."}]
                        },
                    },
                }
            }
        ),
        json.dumps(
            {
                "result": {
                    "kind": "status-update",
                    "contextId": "conv-2",
                    "taskId": "task-2",
                    "final": True,
                    "status": {
                        "state": "completed",
                        "message": {
                            "parts": [
                                {
                                    "kind": "text",
                                    "text": json.dumps(
                                        {
                                            "status": "completed",
                                            "message": "SVG ready.",
                                        }
                                    ),
                                }
                            ]
                        },
                    },
                }
            }
        ),
    ]
    statuses = []

    async def _status_callback(message: str) -> None:
        statuses.append(message)

    class _StreamingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, **kwargs):
            return _FakeStreamingResponse(streamed_lines, content_type="application/x-ndjson")

    monkeypatch.setattr(tool_discovery.httpx, "AsyncClient", _StreamingClient)

    result = asyncio.run(
        tool_discovery.call_a2a_agent(
            "http://example.test/a2a/artifact-debug-agent",
            "create_svg_artifact",
            conversation_id="conv-2",
            word="secure",
            _prefer_streaming=True,
            _status_callback=_status_callback,
        )
    )

    assert statuses == ["Rendering SVG..."]
    assert result["status"] == "completed"
    assert result["message"] == "SVG ready."


def test_apply_stream_event_fires_background_callback_on_flag() -> None:
    """A status event tagged metadata.background invokes the background callback
    (declare_long_running → proactive detach)."""
    fired: list = []

    async def bg(meta):
        fired.append(meta)

    envelope = {
        "result": {
            "kind": "status-update",
            "metadata": {"background": True, "estimate_seconds": 30},
            "status": {},
            "final": False,
        }
    }
    asyncio.run(
        tool_discovery._apply_a2a_stream_event(
            {"kind": "task", "artifacts": []}, envelope, background_callback=bg
        )
    )
    assert fired and fired[0]["background"] is True
    assert fired[0]["estimate_seconds"] == 30


def test_apply_stream_event_heartbeat_does_not_fire_background() -> None:
    """Heartbeats short-circuit before the background check, so they never
    trigger a detach even if (defensively) tagged."""
    fired: list = []

    async def bg(meta):
        fired.append(meta)

    envelope = {"result": {"kind": "status-update", "metadata": {"heartbeat": True, "background": True}}}
    asyncio.run(
        tool_discovery._apply_a2a_stream_event(
            {"kind": "task", "artifacts": []}, envelope, background_callback=bg
        )
    )
    assert fired == []
