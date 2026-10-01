"""Targeted tests for orchestrator execution-path selection."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
import types

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

if "langchain_core.tools" not in sys.modules:
    tools_module = types.ModuleType("langchain_core.tools")

    class _StructuredTool:
        @staticmethod
        def from_function(*args, **kwargs):
            return SimpleNamespace(name=kwargs.get("name", "tool"), invoke=lambda tool_args: {})

    tools_module.StructuredTool = _StructuredTool
    sys.modules["langchain_core.tools"] = tools_module

if "prometheus_api.agent" not in sys.modules:
    prometheus_api_module = sys.modules.get(
        "prometheus_api", types.ModuleType("prometheus_api")
    )
    agent_api_module = types.ModuleType("prometheus_api.agent")

    class _ArtifactReference:
        def __init__(self, **kwargs):
            self.artifact_id = kwargs.get("artifact_id")
            self.conversation_id = kwargs.get("conversation_id")
            self.name = kwargs.get("name")
            self.description = kwargs.get("description")
            self.uri = kwargs.get("uri")
            self.metadata = kwargs.get("metadata") or {}
            self.json_type = kwargs.get("json_type")
            self.json_body = kwargs.get("json_body")

        @classmethod
        def from_any(cls, artifact, conversation_id=None):
            if not isinstance(artifact, dict):
                return None
            metadata = dict(artifact.get("metadata") or {})
            parts = artifact.get("parts") or []
            uri = artifact.get("uri")
            json_type = artifact.get("json_type")
            json_body = artifact.get("json_body")
            for part in parts:
                if not isinstance(part, dict):
                    continue
                kind = str(part.get("kind") or "").strip().lower()
                if kind == "file":
                    file_payload = part.get("file") or {}
                    uri = file_payload.get("uri") or uri
                elif kind == "data":
                    json_body = part.get("data")
                    part_meta = dict(part.get("metadata") or {})
                    json_type = part_meta.get("json_type") or json_type
                    metadata = {**part_meta, **metadata}
            return cls(
                artifact_id=artifact.get("artifact_id") or artifact.get("artifactId"),
                conversation_id=conversation_id or metadata.get("conversation_id"),
                name=artifact.get("name"),
                description=artifact.get("description"),
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

    class _PrometheusAgent:
        def __init__(self, *args, **kwargs):
            self.artifact_registry = SimpleNamespace(register=lambda reference: None)

        @staticmethod
        def pending_hint(pending_requests, hint):
            return hint

        @staticmethod
        def registry_url() -> str:
            return "http://litellm:4000"

        def run(self, *args, **kwargs):
            return None

        def list_artifact_references(self, *args, **kwargs):
            return []

        async def send_status_update(self, *args, **kwargs):
            return None

    agent_api_module.ArtifactReference = _ArtifactReference
    agent_api_module.EventQueue = object
    agent_api_module.PrometheusAgent = _PrometheusAgent
    agent_api_module.RequestContext = object
    prometheus_api_module.agent = agent_api_module
    sys.modules["prometheus_api"] = prometheus_api_module
    sys.modules["prometheus_api.agent"] = agent_api_module

import agent as agent_module  # noqa: E402
import file_upload_handler  # noqa: E402
import planner  # noqa: E402


def test_prior_capability_params_include_followup_values_after_success() -> None:
    params = agent_module._chat_flow._successful_prior_capability_params(
        {
            "routing_decision": {
                "primary_skill": "author_equipment_geometry",
                "capability_params": {
                    "author_equipment_geometry": {
                        "input_data": {
                            "equipment_type": "butterfly_valve",
                            "pipe_diameter": 0.9,
                            "num_holes": 6,
                            "hole_diameter": 0.05,
                        }
                    }
                },
                "extracted_params": {
                    "input_data": {
                        "equipment_type": "butterfly_valve",
                        "pipe_diameter": 0.9,
                        "num_holes": 6,
                        "hole_diameter": 0.05,
                        "rod_diameter": 0.08,
                    }
                },
            },
            "tool_results": {
                "author_equipment_geometry": {"answer": "Created valve geometry"}
            },
        }
    )

    assert params["author_equipment_geometry"]["input_data"]["rod_diameter"] == 0.08


def test_prior_capability_params_use_actual_successful_invocation_inputs() -> None:
    params = agent_module._chat_flow._successful_prior_capability_params(
        {
            "routing_decision": {
                "primary_skill": "author_equipment_geometry",
                "supporting_skills": ["mesh_geometry"],
                "capability_params": {
                    "author_equipment_geometry": {"message": "Create the valve."},
                    "mesh_geometry": {"cad_artifact_id": "old-step"},
                },
            },
            "tool_results": {
                "author_equipment_geometry": {"answer": "Created valve geometry"},
                "mesh_geometry": {"answer": "Meshed valve geometry"},
            },
            "conversation_history": [
                {
                    "role": "assistant",
                    "tool_inputs": {
                        "author_equipment_geometry": {"message": "Create the valve."},
                        "mesh_geometry": {"cad_artifact_id": "new-step"},
                    },
                    "tool_results": {
                        "author_equipment_geometry": {
                            "answer": "Created valve geometry"
                        },
                        "mesh_geometry": {"answer": "Meshed valve geometry"},
                    },
                }
            ],
        }
    )

    assert params["mesh_geometry"]["cad_artifact_id"] == "new-step"


def test_resumed_transcript_records_schema_shaped_inputs() -> None:
    params = agent_module._execution._resumed_transcript_params(
        {
            "input_data": {
                "equipment_type": "butterfly_valve",
                "hole_diameter": 0.05,
            },
            "artifacts": [{"artifact_id": "step-1"}],
        },
        {"rod_diameter": 0.08},
        {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "object",
                    "properties": {
                        "equipment_type": {"type": "string"},
                        "hole_diameter": {"type": "number"},
                        "rod_diameter": {"type": "number"},
                    },
                }
            },
        },
    )

    assert params == {
        "input_data": {
            "equipment_type": "butterfly_valve",
            "hole_diameter": 0.05,
            "rod_diameter": 0.08,
        }
    }


def test_configured_max_upload_bytes_defaults_to_100_mb(monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_MAX_UPLOAD_BYTES", raising=False)
    assert file_upload_handler.configured_max_upload_bytes() == file_upload_handler.DEFAULT_MAX_UPLOAD_BYTES


def test_configured_max_upload_bytes_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("PROMETHEUS_MAX_UPLOAD_BYTES", "4096")
    assert file_upload_handler.configured_max_upload_bytes() == 4096


def test_configured_max_upload_bytes_rejects_invalid_env(monkeypatch) -> None:
    monkeypatch.setenv("PROMETHEUS_MAX_UPLOAD_BYTES", "-1")
    with pytest.raises(ValueError, match="PROMETHEUS_MAX_UPLOAD_BYTES must be positive"):
        file_upload_handler.configured_max_upload_bytes()

def test_runtime_status_stream_emits_store_updates(monkeypatch) -> None:
    emitted = []

    class _Redis:
        def set(self, *args, **kwargs):
            return None

        def rpush(self, *args, **kwargs):
            return None

        def ltrim(self, *args, **kwargs):
            return None

        def expire(self, *args, **kwargs):
            return None

    async def emit_status(message: str) -> None:
        emitted.append(message)

    monkeypatch.setattr(agent_module._runtime, "_get_status_redis_client", lambda: _Redis())

    async def run_stream():
        with agent_module._runtime.status_stream(emit_status) as tasks:
            agent_module._runtime.store_status_update("conv-1", "Streaming status 1.")
            agent_module._runtime.store_status_update("conv-1", "Streaming status 2.")
            await agent_module._runtime.wait_for_status_stream(tasks)

    asyncio.run(run_stream())

    assert emitted == ["Streaming status 1.", "Streaming status 2."]


def test_upload_files_to_deeplynx_consumes_staged_upload(monkeypatch, tmp_path) -> None:
    stage_dir = tmp_path / "staged"
    monkeypatch.setenv("PROMETHEUS_STAGED_UPLOAD_DIR", str(stage_dir))

    upload_id = file_upload_handler.new_staged_upload_id()
    data_path, meta_path = file_upload_handler.staged_upload_paths(upload_id)
    data_path.parent.mkdir(parents=True)
    data_path.write_bytes(b"exodus bytes")
    file_upload_handler.write_staged_upload_metadata(
        upload_id,
        {
            "upload_id": upload_id,
            "name": "mesh.e",
            "mime_type": "application/x-exodus",
            "size_bytes": 12,
        },
    )
    captured = {}

    class _Agent:
        async def send_deeplynx_artifact(self, **kwargs):
            captured.update(kwargs)
            captured["bytes"] = Path(kwargs["file_path"]).read_bytes()
            return agent_module.ArtifactReference(
                artifact_id="artifact-1",
                conversation_id="conv-1",
                name=kwargs["name"],
                description=kwargs["description"],
                uri="deeplynx://file/1",
                metadata={},
            )

    refs = asyncio.run(
        file_upload_handler.upload_files_to_deeplynx(
            _Agent(),
            [
                file_upload_handler.UploadedFile(
                    name="mesh.e",
                    mime_type="application/x-exodus",
                    size_bytes=12,
                    upload_id=upload_id,
                )
            ],
            {"mesh.e": "Uploaded Exodus mesh."},
            context=object(),
            event_queue=object(),
            storage_config=object(),
        )
    )

    assert refs[0].artifact_id == "artifact-1"
    assert captured["bytes"] == b"exodus bytes"
    assert captured["name"] == "mesh.e"
    assert not data_path.exists()
    assert not meta_path.exists()


def test_upload_files_to_deeplynx_rejects_staged_upload_size_mismatch(monkeypatch, tmp_path) -> None:
    stage_dir = tmp_path / "staged"
    monkeypatch.setenv("PROMETHEUS_STAGED_UPLOAD_DIR", str(stage_dir))

    upload_id = file_upload_handler.new_staged_upload_id()
    data_path, meta_path = file_upload_handler.staged_upload_paths(upload_id)
    data_path.parent.mkdir(parents=True)
    data_path.write_bytes(b"abc")
    file_upload_handler.write_staged_upload_metadata(
        upload_id,
        {
            "upload_id": upload_id,
            "name": "mesh.e",
            "mime_type": "application/x-exodus",
            "size_bytes": 3,
        },
    )

    class _Agent:
        async def send_deeplynx_artifact(self, **kwargs):
            raise AssertionError("Mismatched staged upload metadata must not be persisted.")

    refs = asyncio.run(
        file_upload_handler.upload_files_to_deeplynx(
            _Agent(),
            [
                file_upload_handler.UploadedFile(
                    name="mesh.e",
                    mime_type="application/x-exodus",
                    size_bytes=4,
                    upload_id=upload_id,
                )
            ],
            {"mesh.e": "Uploaded Exodus mesh."},
            context=object(),
            event_queue=object(),
            storage_config=object(),
        )
    )

    assert refs == []
    assert not data_path.exists()
    assert not meta_path.exists()


def test_execute_current_plan_routes_templates_through_workflow_engine(monkeypatch) -> None:
    workflow = SimpleNamespace(
        definition=SimpleNamespace(
            id="wf",
            version="1.0.0",
            steps=[SimpleNamespace(id="step-1", skill_id="convert_svg_to_png")],
        )
    )
    registry = SimpleNamespace(get=lambda workflow_id, version=None: workflow)
    calls = {"workflow": 0, "direct": 0}

    async def fake_execute_workflow(**kwargs):
        calls["workflow"] += 1
        return {
            "final_output": "render complete",
            "step_statuses": {"step-1": "succeeded"},
            "step_results": {
                "step-1": {
                    "skill_id": "convert_svg_to_png",
                    "result": {"answer": "render complete"},
                }
            },
        }

    async def fake_invoke_agent_generic(state):
        calls["direct"] += 1
        return {}

    monkeypatch.setattr(agent_module, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "execute_workflow", fake_execute_workflow)
    monkeypatch.setattr(agent_module, "invoke_agent_generic", fake_invoke_agent_generic)

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "workflow_type": "workflow_template",
            "workflow_id": "wf",
            "workflow_version": "1.0.0",
            "extracted_params": {},
        },
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    result = asyncio.run(agent_module.execute_current_plan(state, start_message="go"))

    assert calls == {"workflow": 1, "direct": 0}
    assert result["final_report"] == "render complete"


def test_execute_current_plan_rejects_unhealthy_agent_provided_workflow(monkeypatch) -> None:
    workflow = SimpleNamespace(
        definition=SimpleNamespace(
            id="wf",
            version="1.0.0",
            metadata=SimpleNamespace(
                source_agent_id="thermal-agent",
                source_agent_url="http://thermal-agent:8000",
            ),
            steps=[SimpleNamespace(id="step-1", skill_id="analyze_thermal")],
        )
    )
    registry = SimpleNamespace(get=lambda workflow_id, version=None: workflow)
    calls = {"workflow": 0}

    async def fake_health_check(compiled_workflow):
        assert compiled_workflow is workflow
        return "Workflow provider agent 'thermal-agent' is unavailable."

    async def fake_execute_workflow(**kwargs):
        calls["workflow"] += 1
        return {}

    statuses: list[tuple] = []

    monkeypatch.setattr(agent_module, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "verify_workflow_source_health", fake_health_check)
    monkeypatch.setattr(agent_module, "execute_workflow", fake_execute_workflow)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: statuses.append(args))

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "workflow_type": "workflow_template",
            "workflow_id": "wf",
            "workflow_version": "1.0.0",
            "extracted_params": {},
        },
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    with pytest.raises(RuntimeError, match="thermal-agent"):
        asyncio.run(agent_module.execute_current_plan(state, start_message="go"))

    assert calls["workflow"] == 0
    assert any("thermal-agent" in args[1] for args in statuses if len(args) > 1)


def test_execute_current_plan_reports_tool_errors_in_final_status(monkeypatch) -> None:
    statuses = []

    async def fake_invoke_agent_generic(state):
        return {
            "conversation_history": state.get("conversation_history", []) + [{
                "role": "assistant",
                "content": "[import_step_file] Error: build123d export failed",
                "type": "error",
            }],
            "tool_results": {
                "import_step_file": {"error": "build123d export failed"},
            },
            "awaiting_approval": False,
        }

    monkeypatch.setattr(agent_module, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(agent_module, "invoke_agent_generic", fake_invoke_agent_generic)
    monkeypatch.setattr(
        agent_module,
        "store_status_update",
        lambda conversation_id, message, final=False: statuses.append((message, final)),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "workflow_type": "single",
            "primary_skill": "import_step_file",
            "supporting_skills": [],
            "extracted_params": {},
        },
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    result = asyncio.run(agent_module.execute_current_plan(state, start_message="go"))

    assert result["final_report"] == "[import_step_file] Error: build123d export failed"
    assert statuses[-1] == ("Execution finished with errors.", True)


def test_chat_returns_incomplete_plan_and_form_for_missing_required_params(monkeypatch) -> None:
    async def fake_compile_query_plan(state, **kwargs):
        return {
            "routing_decision": {
                "primary_skill": "analyze_corrosion",
                "supporting_skills": [],
                "workflow_type": "single",
                "extracted_params": {
                    "material_id": "SS316",
                    "context": {"temperature_c": 300},
                },
                "requires_approval": True,
                "required_params": [
                    "context.pressure_mpa",
                    "context.temperature_c",
                    "material_id",
                ],
                "missing_required_params": ["context.pressure_mpa"],
            },
            "plan": {
                "intent": "Analyze corrosion risk in high-temperature water",
                "workflow_type": "single",
                "skills": ["analyze_corrosion"],
                "required_params": [
                    "context.pressure_mpa",
                    "context.temperature_c",
                    "material_id",
                ],
                "steps": ["Invoke analyze_corrosion"],
                "missing_info": ["context.pressure_mpa"],
                "estimated_duration_seconds": 5,
                "param_metadata": {},
            },
            "missing_info": ["context.pressure_mpa"],
            "context": {"temperature_c": 300},
            "material_id": "SS316",
        }

    async def fake_get_capability_by_skill_id(skill_id):
        assert skill_id == "analyze_corrosion"
        return SimpleNamespace(
            input_schema={
                "type": "object",
                "properties": {
                    "material_id": {"type": "string"},
                    "context": {
                        "type": "object",
                        "properties": {
                            "temperature_c": {"type": "number"},
                            "pressure_mpa": {
                                "type": "number",
                                "description": "Operating pressure in MPa",
                            },
                        },
                        "required": ["temperature_c", "pressure_mpa"],
                    },
                },
                "required": ["material_id", "context"],
            }
        )

    async def should_not_extract(*args, **kwargs):
        raise AssertionError("Initial turn should not auto-extract missing follow-up answers from the query.")

    monkeypatch.setattr(agent_module, "compile_query_plan", fake_compile_query_plan)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id
        ),
    )
    monkeypatch.setattr(agent_module, "extract_followup_answers_from_query", should_not_extract)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_conversation", lambda conversation_id, state: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query=(
                    "Analyze corrosion risk for SS316 in a high-temperature "
                    "water environment at 300 C."
                ),
                conversation_id="conv-1",
            )
        )
    )

    assert response.status == "needs_info"
    assert response.followup_questions == [
        {
            "field": "context.pressure_mpa",
            "question": "Operating pressure in MPa",
            "type": "number",
        }
    ]
    assert response.plan["skills"] == ["analyze_corrosion"]
    assert response.plan["required_params"] == [
        "context.pressure_mpa",
        "context.temperature_c",
        "material_id",
    ]


def test_structured_followup_entry_preserves_answers() -> None:
    entry = agent_module._chat_flow._structured_followup_entry(None, {"input_data.rod_diameter": 0.08})

    assert entry["provided_inputs"] == {"input_data.rod_diameter": 0.08}


def test_chat_exposes_received_files_to_planner_context(monkeypatch) -> None:
    seen = {}

    async def fake_compile_query_plan(state, **kwargs):
        seen["context"] = state.get("context")
        return {
            "is_fallback": True,
            "fallback_message": "ok",
        }

    monkeypatch.setattr(agent_module, "compile_query_plan", fake_compile_query_plan)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_conversation", lambda conversation_id, state: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query="What can you do with this?",
                conversation_id="conv-uploads",
                received_files=[
                    {
                        "name": "model.ifc",
                        "mime_type": "application/ifc",
                        "size_bytes": 12,
                    }
                ],
            )
        )
    )

    assert response.status == "answer"
    assert seen["context"]["received_files"] == [
        {
            "name": "model.ifc",
            "mime_type": "application/ifc",
            "size_bytes": 12,
        }
    ]


def test_chat_does_not_expose_internal_planning_tool_names(monkeypatch) -> None:
    status_updates = []

    async def malformed_plan(*args, **kwargs):
        raise planner.PlanningContractError(
            "Parameter extraction did not call required tool(s): extract_2_convert_svg_to_png"
        )

    monkeypatch.setattr(agent_module, "compile_query_plan", malformed_plan)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_conversation", lambda conversation_id, state: None)
    monkeypatch.setattr(
        agent_module,
        "store_status_update",
        lambda conversation_id, message, **kwargs: status_updates.append(message),
    )

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query="Create a CAD valve and mesh it.",
                conversation_id="conv-contract-error",
            )
        )
    )

    assert response.status == "error"
    assert response.message == (
        "I couldn't build a valid execution plan for this request. Please try again."
    )
    assert "extract_2_convert_svg_to_png" not in response.message
    assert any("extract_2_convert_svg_to_png" in update for update in status_updates)


def test_agents_slash_command_lists_registered_agents_without_planner(monkeypatch) -> None:
    async def should_not_compile(*args, **kwargs):
        raise AssertionError("Slash commands must not invoke the planner LLM.")

    async def fake_discover_agents():
        return [
            {
                "agent_id": "mesh-agent",
                "name": "Mesh Agent",
                "url": "http://mesh-agent:8000",
                "agent_card_params": {
                    "skills": [{"id": "inspect_mesh", "name": "Inspect Mesh"}],
                },
            }
        ]

    async def fake_get_capabilities():
        return [
            SimpleNamespace(
                agent_id="mesh-agent",
                agent_name="Mesh Agent",
                agent_url="http://litellm:4000/a2a/mesh-agent",
                skill_id="convert_mesh",
                skill_name="Convert Mesh",
            )
        ]

    monkeypatch.setattr(agent_module, "compile_query_plan", should_not_compile)
    monkeypatch.setattr(agent_module, "discover_agents", fake_discover_agents)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(query="/agents", conversation_id="conv-debug")
        )
    )

    assert response.status == "answer"
    assert "Registered agents (1)" in response.message
    assert "Mesh Agent (mesh-agent)" in response.message
    assert "inspect_mesh (Inspect Mesh)" in response.message
    assert "convert_mesh (Convert Mesh)" in response.message
    assert response.message_metadata["slash_command"] == "agents"


def test_artifacts_slash_command_lists_conversation_artifacts_without_planner(monkeypatch) -> None:
    async def should_not_compile(*args, **kwargs):
        raise AssertionError("Slash commands must not invoke the planner LLM.")

    monkeypatch.setattr(agent_module, "compile_query_plan", should_not_compile)
    monkeypatch.setattr(
        agent_module,
        "get_conversation",
        lambda conversation_id: {
            "missing_info": ["context.temperature_c"],
            "context": {
                "artifacts": [
                    {
                        "artifact_id": "older-1",
                        "name": "older-result.json",
                        "description": "Earlier analysis output.",
                        "json_body": {"ok": True},
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query="/artifacts",
                conversation_id="conv-debug",
                artifacts=[
                    {
                        "artifact_id": "svg-1",
                        "name": "diagram.svg",
                        "description": "Uploaded SVG.",
                        "uri": "deeplynx://container/file/123",
                        "mime_type": "image/svg+xml",
                        "metadata": {
                            "source": "user-upload",
                            "deeplynx_file_id": 123,
                        },
                    }
                ],
            )
        )
    )

    assert response.status == "answer"
    assert "Conversation artifacts (2)" in response.message
    assert "diagram.svg" in response.message
    assert "deeplynx_file_id: 123" in response.message
    assert "older-result.json" in response.message
    assert [artifact["artifact_id"] for artifact in response.artifacts] == ["svg-1", "older-1"]


def test_workflows_slash_command_lists_platform_and_agent_workflows(monkeypatch) -> None:
    async def should_not_compile(*args, **kwargs):
        raise AssertionError("Slash commands must not invoke the planner LLM.")

    catalog = [
        {
            "id": "platform.safety_check",
            "version": "1.0.0",
            "display_name": "Platform Safety Check",
            "summary": "Run the platform safety checks.",
            "category": "Safety",
            "requires_approval": True,
            "estimated_duration_seconds": 60,
            "owner": "platform-team",
            "source": "local",
        },
        {
            "id": "thermal.quick_check",
            "version": "2.1.0",
            "display_name": "Quick Thermal Check",
            "summary": "Run the agent's thermal checks.",
            "category": "Thermal",
            "requires_approval": False,
            "estimated_duration_seconds": 30,
            "owner": "thermal-agent",
            "source": "agent_card",
        },
    ]
    registry = SimpleNamespace(get_catalog=lambda: catalog)

    monkeypatch.setattr(agent_module, "compile_query_plan", should_not_compile)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(query="/workflows", conversation_id="conv-workflows")
        )
    )

    assert response.status == "answer"
    assert "Registered workflows (2)" in response.message
    assert "Platform-owned workflows (1)" in response.message
    assert "Agent-owned workflows (1)" in response.message
    assert "Platform Safety Check (`/platform_safety_check`)" in response.message
    assert "Quick Thermal Check (`/thermal_quick_check`)" in response.message
    assert "owner: thermal-agent" in response.message
    assert response.message_metadata == {
        "slash_command": "workflows",
        "workflows": catalog,
    }


def test_help_slash_command_lists_builtin_and_workflow_commands(monkeypatch) -> None:
    async def should_not_compile(*args, **kwargs):
        raise AssertionError("Slash commands must not invoke the planner LLM.")

    registry = SimpleNamespace(
        get_catalog=lambda: [
            {
                "id": "thermal.quick_check",
                "version": "2.1.0",
                "display_name": "Quick Thermal Check",
                "summary": "Run the agent's thermal checks.",
                "category": "Thermal",
                "requires_approval": False,
                "estimated_duration_seconds": 30,
                "owner": "thermal-agent",
                "source": "agent_card",
            }
        ]
    )

    monkeypatch.setattr(agent_module, "compile_query_plan", should_not_compile)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(query="/help", conversation_id="conv-help")
        )
    )

    assert response.status == "answer"
    assert "Available commands (7)" in response.message
    for command in ("agents", "artifacts", "forget", "help", "tasks", "workflows"):
        assert f"`/{command}`" in response.message
    assert "Workflow commands (1)" in response.message
    assert "`/thermal_quick_check`" in response.message
    assert response.message_metadata == {
        "slash_command": "help",
        "supported_commands": ["agents", "artifacts", "forget", "help", "tasks", "workflows"],
        "workflow_commands": [
            {
                "command": "thermal_quick_check",
                "workflow_id": "thermal.quick_check",
                "workflow_version": "2.1.0",
                "display_name": "Quick Thermal Check",
            }
        ],
    }


def test_workflow_slash_command_forces_explicit_workflow(monkeypatch) -> None:
    workflow = SimpleNamespace(
        required_input_paths=[],
        definition=SimpleNamespace(
            id="artifact_debug.patriotic_usa_png",
            version="1.0.0",
            name="Patriotic USA PNG",
            steps=[],
            ui=SimpleNamespace(display_name="Patriotic USA PNG"),
        ),
    )
    registry = SimpleNamespace(
        list_all=lambda: [workflow],
        get=lambda workflow_id, version=None: workflow
        if workflow_id == "artifact_debug.patriotic_usa_png"
        else None,
    )
    seen = {}

    async def fake_compile_query_plan(state, **kwargs):
        seen["state"] = state
        seen["kwargs"] = kwargs
        return {"is_fallback": True, "fallback_message": "planned"}

    monkeypatch.setattr(agent_module, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "compile_query_plan", fake_compile_query_plan)
    monkeypatch.setattr(
        agent_module,
        "get_conversation",
        lambda conversation_id: {
            "missing_info": ["stale_param"],
            "conversation_history": [{"role": "user", "content": "previous turn"}],
            "context": {"existing": "context"},
        },
    )
    monkeypatch.setattr(agent_module, "store_conversation", lambda conversation_id, state: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query="/patriotic_usa_png Happy fourth of July",
                conversation_id="conv-workflow-slash",
            )
        )
    )

    assert response.status == "answer"
    assert seen["state"]["user_query"] == "Happy fourth of July"
    assert seen["state"]["context"]["existing"] == "context"
    assert seen["kwargs"]["explicit_workflow_id"] == "artifact_debug.patriotic_usa_png"
    assert seen["kwargs"]["explicit_workflow_version"] == "1.0.0"
    assert seen["kwargs"]["selection_source"] == "slash_command"


class _NullEventQueue:
    """``_execute`` sends status updates; the base class enqueues them here."""

    async def enqueue_event(self, event):
        pass


def test_execute_slash_command_skips_upload_and_lazy_refresh(monkeypatch) -> None:
    async def should_not_refresh(*args, **kwargs):
        raise AssertionError("Slash commands should not refresh tool caches before handling.")

    async def should_not_upload(*args, **kwargs):
        raise AssertionError("Slash commands should not process uploaded files.")

    monkeypatch.setattr(agent_module, "_tools_cache", None)
    monkeypatch.setattr(agent_module, "refresh_dynamic_components", should_not_refresh)
    monkeypatch.setattr(agent_module.OrchestratorAgent, "_handle_uploaded_files", should_not_upload)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    artifact = SimpleNamespace(
        artifact_id="artifact-1",
        to_dict=lambda: {
            "artifact_id": "artifact-1",
            "conversation_id": "conv-debug",
            "name": "diagram.svg",
            "description": "Registered SVG.",
            "uri": "deeplynx://container/file/123",
            "mime_type": "image/svg+xml",
        },
    )
    orchestrator = agent_module.OrchestratorAgent()
    orchestrator.list_artifact_references = lambda *args, **kwargs: [artifact]

    payload = asyncio.run(
        orchestrator._execute(
            {
                "query": "/artifacts",
                "conversation_id": "conv-debug",
                "uploaded_files": [
                    {
                        "name": "ignored.svg",
                        "mime_type": "image/svg+xml",
                        "size_bytes": 12,
                        "upload_id": "0" * 32,
                    }
                ],
            },
            SimpleNamespace(context_id="conv-debug"),
            _NullEventQueue(),
        )
    )

    assert payload["status"] == "answer"
    assert "diagram.svg" in payload["message"]
    assert payload["artifacts"][0]["artifact_id"] == "artifact-1"
    assert payload["new_artifacts"] == []


def test_execute_detaches_when_agent_declares_long_running(monkeypatch) -> None:
    """When a dispatched agent calls declare_long_running mid-turn (signalled via
    task_tracking.request_background), _execute detaches and returns a
    backgrounded response — even with the soft deadline disabled.

    Exercises service.OrchestratorAgent directly (the base _execute) to bypass
    agent.py's compat layer, which re-exports service.chat on every call.
    """
    import orchestrator.service as service_mod
    import task_graph
    from orchestrator import task_tracking
    from tests.test_task_graph import _FakeRedis

    fake_redis = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake_redis)
    task_tracking._turn.set(None)
    task_tracking._nested_parent.set(None)

    monkeypatch.delenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", raising=False)  # deadline off
    monkeypatch.setattr(service_mod.runtime, "_tools_cache", [object()])  # skip lazy refresh
    monkeypatch.setattr(service_mod.runtime, "store_status_update", lambda *a, **k: None)
    monkeypatch.setattr(service_mod, "get_conversation", lambda conversation_id: None)

    async def no_upload(self, *args, **kwargs):
        return []

    monkeypatch.setattr(service_mod.OrchestratorAgent, "_handle_uploaded_files", no_upload)

    async def fake_chat(request):
        # Simulate a dispatched agent declaring itself long-running, then keep
        # working (so the race resolves on the background signal, not chat).
        task_tracking.request_background()
        await asyncio.sleep(0.05)
        return service_mod.ConversationResponse(
            conversation_id="conv-bg", status="completed", report="eventually"
        )

    monkeypatch.setattr(service_mod, "chat", fake_chat)

    captured: dict = {}

    def fake_spawn(self, chat_task, conversation_id, root_id, turn):
        captured["root_id"] = root_id
        chat_task.cancel()  # don't leave the slow task running past the test

    monkeypatch.setattr(service_mod.OrchestratorAgent, "_spawn_background_finisher", fake_spawn)

    orchestrator = service_mod.OrchestratorAgent()
    orchestrator.list_artifact_references = lambda *args, **kwargs: []

    payload = asyncio.run(
        orchestrator._execute(
            {"query": "run a long simulation", "conversation_id": "conv-bg"},
            SimpleNamespace(context_id="conv-bg"),
            _NullEventQueue(),
        )
    )

    assert payload["status"] == "backgrounded"
    assert payload["message_metadata"]["task_id"] == captured["root_id"]


def test_invoke_agent_generic_passes_artifact_catalog_to_skill(monkeypatch) -> None:
    captured = {}

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        captured["skill_id"] = skill_id
        captured["params"] = params
        captured["conversation_id"] = conversation_id
        return {"skill_id": skill_id, "result": {"message": "converted"}}

    async def fake_get_capability_by_skill_id(skill_id):
        return None

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capability_by_skill_id=fake_get_capability_by_skill_id),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "convert_svg_to_png",
            "supporting_skills": [],
            "workflow_type": "single",
            "extracted_params": {"artifact_id": "svg-1"},
        },
        "context": {
            "artifacts": [
                {
                    "artifact_id": "svg-1",
                    "name": "diagram.svg",
                    "uri": "deeplynx://organizations/1/projects/1/items/99",
                    "metadata": {"deeplynx_file_id": 123},
                }
            ]
        },
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert result["tool_results"]["convert_svg_to_png"] == {"message": "converted"}
    assert captured["conversation_id"] == "conv-1"
    assert captured["params"]["artifact_id"] == "svg-1"
    assert captured["params"]["artifacts"] == [
        {
            "artifact_id": "svg-1",
            "name": "diagram.svg",
            "description": "",
            "uri": "deeplynx://organizations/1/projects/1/items/99",
            "mime_type": None,
            "size_bytes": None,
            "producer_agent_id": None,
            "created_at": None,
            "tags": [],
            "metadata": {"deeplynx_file_id": 123},
        }
    ]


def test_find_tool_for_skill_uses_runtime_tool_cache(monkeypatch) -> None:
    tool = SimpleNamespace(name="create_svg_artifact")

    monkeypatch.setattr(agent_module._runtime, "_tools_cache", [tool])

    result = asyncio.run(
        agent_module.find_tool_for_skill(
            "create_svg_artifact",
            refresh_on_miss=False,
        )
    )

    assert result is tool


def test_invoke_skill_validates_nested_required_paths(monkeypatch) -> None:
    capability = SimpleNamespace(
        input_schema={
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
        }
    )

    class _UnexpectedTool:
        async def ainvoke(self, params):
            raise AssertionError("Tool should not be invoked when nested required params are missing.")

    async def fake_find_tool_for_skill(*args, **kwargs):
        return _UnexpectedTool()

    async def fake_get_capability_by_skill_id(skill_id):
        return capability

    monkeypatch.setattr(
        agent_module,
        "find_tool_for_skill",
        fake_find_tool_for_skill,
    )
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capability_by_skill_id=fake_get_capability_by_skill_id),
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    result = asyncio.run(
        agent_module.invoke_skill(
            "analyze_thermal",
            {"material_id": "SS316"},
            "conv-1",
        )
    )

    assert result["missing_required_params"] == ["context.temperature_c"]


def test_ask_followup_dynamic_uses_pending_subagent_request() -> None:
    state = {
        "conversation_history": [],
        "pending_subagent_requests": [
            {
                "skill_id": "author_equipment_geometry",
                "missing_inputs": [
                    {
                        "name": "hole_diameter",
                        "description": "Diameter of each through-hole, in metres.",
                        "user_prompt": "Hole diameter (m)",
                        "type": "number",
                        "options": None,
                        "resolvable_from_context": False,
                        "sensitive": False,
                        "required": True,
                    },
                    {
                        "name": "rod_diameter",
                        "description": "Outer diameter of the actuator shaft, in metres.",
                        "user_prompt": "Rod diameter (m)",
                        "type": "number",
                        "options": None,
                        "resolvable_from_context": False,
                        "sensitive": False,
                        "required": True,
                    },
                ],
                "hint": "Butterfly valve dimensions required",
            },
        ],
    }

    result = asyncio.run(agent_module.ask_followup_dynamic(state))

    questions = result["conversation_history"][-1]["questions"]
    assert [(question["field"], question["question"]) for question in questions] == [
        ("hole_diameter", "Hole diameter (m)"),
        ("rod_diameter", "Rod diameter (m)"),
    ]
    assert [question["type"] for question in questions] == ["number", "number"]
    assert result["missing_info"] == ["hole_diameter", "rod_diameter"]


def test_invoke_agent_generic_parallel_preserves_partial_results_on_exception(monkeypatch) -> None:
    """One skill raising must not cancel siblings or discard their results."""

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        if skill_id == "bad_skill":
            raise RuntimeError("boom")
        return {"skill_id": skill_id, "result": {"ok": True}}

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "good_skill",
            "supporting_skills": ["bad_skill"],
            "workflow_type": "parallel",
            "extracted_params": {},
        },
        "context": {},
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert result["tool_results"]["good_skill"] == {"ok": True}
    assert "boom" in result["tool_results"]["bad_skill"]["error"]


def test_chat_plan_rejection_clears_pending_plan(monkeypatch) -> None:
    stored = {}
    existing_state = {
        "conversation_id": "conv-1",
        "awaiting_approval": True,
        "routing_decision": {"workflow_type": "single", "primary_skill": "analyze_thermal"},
        "plan": {"intent": "thermal analysis"},
        "missing_info": [],
        "pending_subagent_requests": [],
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    async def should_not_execute(*args, **kwargs):
        raise AssertionError("Plan rejection must not execute the plan.")

    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: existing_state)
    monkeypatch.setattr(
        agent_module, "store_conversation", lambda conversation_id, state: stored.update({conversation_id: state})
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_module, "execute_approved_plan", should_not_execute)
    monkeypatch.setattr(agent_module, "execute_current_plan", should_not_execute)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(conversation_id="conv-1", plan_rejected=True)
        )
    )

    assert response.status == "answer"
    assert "rejected" in (response.message or "").lower()
    saved = stored["conv-1"]
    assert saved["awaiting_approval"] is False
    assert saved["routing_decision"] is None
    assert saved["plan"] is None
    assert saved["pending_subagent_requests"] == []


def test_execute_current_plan_surfaces_all_input_required_steps(monkeypatch) -> None:
    """Multiple INPUT_REQUIRED workflow steps must all reach the user at once."""
    workflow = SimpleNamespace(
        definition=SimpleNamespace(
            id="wf",
            version="1.0.0",
            steps=[
                SimpleNamespace(id="step-1", skill_id="skill_a"),
                SimpleNamespace(id="step-2", skill_id="skill_b"),
            ],
        )
    )
    registry = SimpleNamespace(get=lambda workflow_id, version=None: workflow)

    async def fake_execute_workflow(**kwargs):
        return {
            "final_output": None,
            "step_statuses": {"step-1": "input_required", "step-2": "input_required"},
            "step_results": {},
            "input_required_steps": [
                {
                    "step_id": "step-1",
                    "skill_id": "skill_a",
                    "_task_graph_root_id": "root-1",
                    "_task_graph_node_id": "node-1",
                    "input_required": {
                        "missing_inputs": [{"name": "temperature_c", "type": "number"}],
                        "hint": "Need temperature",
                    },
                },
                {
                    "step_id": "step-2",
                    "skill_id": "skill_b",
                    "_task_graph_root_id": "root-1",
                    "_task_graph_node_id": "node-2",
                    "input_required": {
                        "missing_inputs": [{"name": "pressure_mpa", "type": "number"}],
                        "hint": "Need pressure",
                    },
                },
            ],
        }

    monkeypatch.setattr(agent_module, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(agent_module, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_module, "execute_workflow", fake_execute_workflow)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "workflow_type": "workflow_template",
            "workflow_id": "wf",
            "workflow_version": "1.0.0",
            "extracted_params": {},
        },
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    result = asyncio.run(agent_module.execute_current_plan(state, start_message="go"))

    pending = result["pending_subagent_requests"]
    assert [entry["skill_id"] for entry in pending] == ["skill_a", "skill_b"]
    assert [entry["task_graph_node_id"] for entry in pending] == ["node-1", "node-2"]
    assert {entry["task_graph_root_id"] for entry in pending} == {"root-1"}
    assert result["missing_info"] == ["temperature_c", "pressure_mpa"]


def test_plan_approval_persists_state_before_execution(monkeypatch) -> None:
    """Regression: approval only cleared awaiting_approval in memory; when
    execution detached to the background, Redis kept awaiting_approval=True
    for the whole run, so a new query (e.g. an unrelated question typed while
    waiting) was misrouted into the plan-refinement branch."""
    import copy

    stored: list = []
    existing_state = {
        "conversation_id": "conv-1",
        "awaiting_approval": True,
        "routing_decision": {"workflow_type": "single", "primary_skill": "analyze_thermal"},
        "plan": {"intent": "thermal analysis"},
        "missing_info": [],
        "pending_subagent_requests": [],
        "conversation_history": [],
        "context": {},
        "tool_results": {},
    }

    async def fake_execute_approved_plan(state):
        # By the time execution starts, the approval must already be durable.
        assert stored, "state was not persisted before execute_approved_plan"
        assert stored[-1]["awaiting_approval"] is False
        return {**state, "final_report": "done", "tool_results": {"analyze_thermal": {"ok": True}}}

    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: existing_state)
    monkeypatch.setattr(
        agent_module,
        "store_conversation",
        lambda conversation_id, state: stored.append(copy.deepcopy(state)),
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_module, "execute_approved_plan", fake_execute_approved_plan)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(conversation_id="conv-1", plan_approved=True)
        )
    )

    assert response.status == "completed"


def test_single_execution_uses_latest_extracted_params(monkeypatch) -> None:
    invoked: dict = {}

    async def no_capability(skill_id):
        return None

    async def fake_extract_parameters_with_schemas(**kwargs):
        raise AssertionError("execution must not re-extract an already resolved plan")

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked.update(params)
        return {"skill_id": skill_id, "result": {"answer": "Nothing."}}

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=no_capability,
            get_by_skill_id=lambda skill_id: None,
        ),
    )

    result = asyncio.run(
        agent_module.invoke_agent_generic(
            {
                "conversation_id": "conv-1",
                "user_query": "What changed in the latest report?",
                "routing_decision": {
                    "primary_skill": "search_literature",
                    "supporting_skills": [],
                    "workflow_type": "single",
                    "extracted_params": {"question": "What changed in the latest report?"},
                    "capability_params": {
                        "search_literature": {
                            "question": "stale planning snapshot"
                        }
                    },
                },
                "context": {},
                "conversation_history": [],
            }
        )
    )

    assert invoked["question"] == "What changed in the latest report?"
    assert result["conversation_history"][-1]["tool_inputs"] == {
        "search_literature": {"question": "What changed in the latest report?"}
    }


def test_sequential_execution_does_not_apply_relative_change_twice(monkeypatch) -> None:
    invoked: dict[str, dict] = {}

    async def fake_extract_parameters_with_schemas(**kwargs):
        if kwargs["capabilities"][0].skill_id == "author_equipment_geometry":
            return {
                "input_data": {
                    "equipment_type": "butterfly_valve",
                    "hole_diameter": 0.2,
                }
            }
        return {"cad_artifact_id": "new-step"}

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked[skill_id] = dict(params)
        if skill_id == "author_equipment_geometry":
            return {
                "skill_id": skill_id,
                "result": {
                    "artifacts": [
                        {
                            "artifact_id": "new-step",
                            "name": "updated.step",
                            "mime_type": "application/step",
                        }
                    ]
                },
            }
        return {"skill_id": skill_id, "result": {"status": "completed"}}

    schemas = {
        "author_equipment_geometry": {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "object",
                    "properties": {
                        "equipment_type": {"type": "string"},
                        "hole_diameter": {"type": "number"},
                    },
                }
            },
        },
        "mesh_geometry": {
            "type": "object",
            "properties": {
                "cad_artifact_id": {
                    "type": "string",
                    "x_artifact_ref": "single",
                }
            },
        },
    }

    async def fake_get_capability_by_skill_id(skill_id):
        return SimpleNamespace(
            skill_id=skill_id,
            input_schema=schemas[skill_id],
            provides=None,
        )

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
            get_by_skill_id=lambda skill_id: None,
        ),
    )

    planned_author_params = {
        "input_data": {
            "equipment_type": "butterfly_valve",
            "hole_diameter": 0.1,
        }
    }
    state = {
        "conversation_id": "conv-1",
        "user_query": "Double the hole diameter, then mesh the updated valve.",
        "routing_decision": {
            "primary_skill": "author_equipment_geometry",
            "supporting_skills": ["mesh_geometry"],
            "workflow_type": "sequential",
            "extracted_params": planned_author_params,
            "capability_params": {
                "author_equipment_geometry": planned_author_params,
            },
            "operations": [
                {
                    "operation_id": "op_1",
                    "description": "Double the valve hole diameter.",
                    "depends_on": [],
                },
                {
                    "operation_id": "op_2",
                    "description": "Mesh the updated valve.",
                    "depends_on": ["op_1"],
                },
            ],
            "operation_coverage": {
                "op_1": "author_equipment_geometry",
                "op_2": "mesh_geometry",
            },
        },
        "context": {},
        "conversation_history": [],
    }

    asyncio.run(agent_module.invoke_agent_generic(state))

    assert invoked["author_equipment_geometry"]["input_data"]["hole_diameter"] == 0.1
    assert invoked["mesh_geometry"]["cad_artifact_id"] == "new-step"


def test_sequential_execution_binds_produced_artifact_to_next_step(monkeypatch) -> None:
    """The canonical resolver maps an upstream artifact into the next schema."""
    captured_params: dict = {}
    resolver_calls: list[dict] = []

    convert_schema = {
        "type": "object",
        "properties": {
            "artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
            }
        },
        "required": ["artifact_id"],
    }

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        captured_params[skill_id] = params
        if skill_id == "create_svg_artifact":
            return {
                "skill_id": skill_id,
                "result": {
                    "status": "success",
                    "artifacts": [{"artifact_id": "svg-123", "name": "image.svg"}],
                },
            }
        return {"skill_id": skill_id, "result": {"status": "success"}}

    async def fake_get_capability_by_skill_id(skill_id):
        if skill_id == "convert_svg_to_png":
            return SimpleNamespace(
                skill_id=skill_id,
                input_schema=convert_schema,
                provides=None,
            )
        return None

    async def fake_extract_parameters_with_schemas(**kwargs):
        resolver_calls.append(kwargs)
        assert kwargs["query"] == "Convert the created SVG to PNG."
        assert kwargs["history"][-1]["tool_results"]["create_svg_artifact"][
            "artifacts"
        ][0]["artifact_id"] == "svg-123"
        assert [
            artifact["artifact_id"]
            for artifact in kwargs["context"]["artifacts"]
        ] == ["svg-123"]
        return {"artifact_id": "svg-123"}

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
            get_by_skill_id=lambda skill_id: None,  # sync lookup used by skill ordering
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "create_svg_artifact",
            "supporting_skills": ["convert_svg_to_png"],
            "workflow_type": "sequential",
            "extracted_params": {"word": "LBNL is a cool lab"},
            "operations": [
                {
                    "operation_id": "op_1",
                    "description": "Create an SVG.",
                    "depends_on": [],
                },
                {
                    "operation_id": "op_2",
                    "description": "Convert the created SVG to PNG.",
                    "depends_on": ["op_1"],
                },
            ],
            "operation_coverage": {
                "op_1": "create_svg_artifact",
                "op_2": "convert_svg_to_png",
            },
        },
        "context": {},
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    # Step 2 received the artifact produced by step 1.
    assert captured_params["convert_svg_to_png"]["artifact_id"] == "svg-123"
    assert len(resolver_calls) == 1
    assert "error" not in result["tool_results"]["convert_svg_to_png"]


def test_sequential_execution_stops_when_step_requires_input(monkeypatch) -> None:
    invoked: list[str] = []

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked.append(skill_id)
        if skill_id == "author_equipment_geometry":
            return {
                "skill_id": skill_id,
                "input_required": {
                    "missing_inputs": [
                        {
                            "name": "rod_diameter",
                            "description": "Outer diameter of the actuator shaft, in metres.",
                            "user_prompt": "Rod diameter (m)",
                            "type": "number",
                            "options": None,
                            "resolvable_from_context": False,
                            "sensitive": False,
                            "required": True,
                        }
                    ],
                    "hint": "Butterfly valve dimensions required",
                },
                "_a2a_context_id": "conv-1",
                "_a2a_task_id": "task-1",
                "_task_graph_root_id": "root-1",
                "_task_graph_node_id": "node-1",
            }
        raise AssertionError("mesh_geometry must wait for the requested input.")

    async def no_capability(skill_id):
        return None

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_by_skill_id=lambda skill_id: None,
            get_capability_by_skill_id=no_capability,
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "author_equipment_geometry",
            "supporting_skills": ["mesh_geometry"],
            "workflow_type": "sequential",
            "extracted_params": {},
        },
        "context": {},
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert invoked == ["author_equipment_geometry"]
    assert result["missing_info"] == ["rod_diameter"]
    assert result["pending_subagent_requests"] == [
        {
            "skill_id": "author_equipment_geometry",
            "a2a_context_id": "conv-1",
            "a2a_task_id": "task-1",
            "task_graph_root_id": "root-1",
            "task_graph_node_id": "node-1",
            "missing_inputs": [
                {
                    "name": "rod_diameter",
                    "description": "Outer diameter of the actuator shaft, in metres.",
                    "user_prompt": "Rod diameter (m)",
                    "type": "number",
                    "options": None,
                    "resolvable_from_context": False,
                    "sensitive": False,
                    "required": True,
                }
            ],
            "hint": "Butterfly valve dimensions required",
        }
    ]


def test_chat_continues_sequential_plan_after_pending_step_resumes(monkeypatch) -> None:
    invoked: list[tuple[str, dict]] = []
    stored: list[dict] = []

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked.append((skill_id, params))
        if skill_id == "author_equipment_geometry":
            assert params["provided_inputs"] == {"rod_diameter": 0.08}
            return {
                "skill_id": skill_id,
                "result": {
                    "message": "CAD created",
                    "artifacts": [{"artifact_id": "cad-1", "name": "valve.step"}],
                },
            }
        if skill_id == "mesh_geometry":
            assert [artifact["artifact_id"] for artifact in params["artifacts"]] == ["cad-1"]
            return {
                "skill_id": skill_id,
                "result": {
                    "message": "Mesh created",
                    "artifacts": [{"artifact_id": "mesh-1", "name": "valve.exo"}],
                },
            }
        raise AssertionError(f"Unexpected skill: {skill_id}")

    async def no_capability(skill_id):
        return None

    existing_state = {
        "conversation_id": "conv-valve",
        "user_query": (
            "create a cad geometry of a butterfly valve with a diameter of 90cm, "
            "4 holes (10cm each), then mesh it"
        ),
        "routing_decision": {
            "primary_skill": "author_equipment_geometry",
            "supporting_skills": ["mesh_geometry"],
            "workflow_type": "sequential",
            "extracted_params": {},
            "requires_approval": False,
        },
        "context": {},
        "conversation_history": [],
        "tool_results": {},
        "missing_info": ["rod_diameter"],
        "pending_subagent_requests": [
            {
                "skill_id": "author_equipment_geometry",
                "a2a_context_id": "a2a-context-1",
                "a2a_task_id": "a2a-task-1",
                "missing_inputs": [
                    {
                        "name": "rod_diameter",
                        "type": "number",
                        "required": True,
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: existing_state)
    monkeypatch.setattr(
        agent_module,
        "store_conversation",
        lambda conversation_id, state: stored.append(state.copy()),
    )
    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_by_skill_id=lambda skill_id: None,
            get_capability_by_skill_id=no_capability,
        ),
    )

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                conversation_id="conv-valve",
                followup_answers={"rod_diameter": 0.08},
            )
        )
    )

    assert response.status == "completed", response.message
    assert [skill_id for skill_id, _ in invoked] == [
        "author_equipment_geometry",
        "mesh_geometry",
    ]
    assert set(response.tool_results) == {"author_equipment_geometry", "mesh_geometry"}
    assert (
        response.tool_results["author_equipment_geometry"]["artifacts"][0]["artifact_id"]
        == "cad-1"
    )
    assert response.tool_results["mesh_geometry"]["artifacts"][0]["artifact_id"] == "mesh-1"
    assert response.report == "CAD created\n\nMesh created"
    assert stored[-1]["pending_subagent_requests"] == []
    assert stored[-1]["routing_decision"]["primary_skill"] == "author_equipment_geometry"
    assert stored[-1]["routing_decision"]["supporting_skills"] == ["mesh_geometry"]
    author_invocations = [
        entry["tool_inputs"]["author_equipment_geometry"]
        for entry in stored[-1]["conversation_history"]
        if "author_equipment_geometry" in (entry.get("tool_inputs") or {})
    ]
    assert author_invocations[-1]["rod_diameter"] == 0.08


def test_resume_pending_subagent_request_preserves_task_graph_identity(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        captured.update(params)
        return {
            "skill_id": skill_id,
            "input_required": {
                "missing_inputs": [
                    {
                        "name": "hole_diameter",
                        "type": "number",
                        "required": True,
                    }
                ],
                "hint": "Hole diameter is still required",
            },
            "_a2a_context_id": "a2a-context-1",
            "_a2a_task_id": "a2a-task-1",
            "_task_graph_root_id": "root-1",
            "_task_graph_node_id": "node-1",
        }

    monkeypatch.setattr(agent_module._execution, "invoke_skill", fake_invoke_skill)
    state = {
        "conversation_id": "conv-1",
        "routing_decision": {"extracted_params": {}},
        "context": {},
        "conversation_history": [],
        "tool_results": {},
        "pending_subagent_requests": [
            {
                "skill_id": "author_equipment_geometry",
                "a2a_context_id": "a2a-context-1",
                "a2a_task_id": "a2a-task-1",
                "task_graph_root_id": "root-1",
                "task_graph_node_id": "node-1",
                "missing_inputs": [
                    {"name": "rod_diameter", "type": "number", "required": True}
                ],
                "hint": "Rod diameter is required",
            }
        ],
    }

    result = asyncio.run(
        agent_module.resume_pending_subagent_requests(
            state,
            {"rod_diameter": "0.05"},
        )
    )

    assert captured["_task_graph_root_id"] == "root-1"
    assert captured["_task_graph_node_id"] == "node-1"
    assert result["pending_subagent_requests"][0]["task_graph_root_id"] == "root-1"
    assert result["pending_subagent_requests"][0]["task_graph_node_id"] == "node-1"


def test_sequential_execution_continues_after_context_resolves_input(monkeypatch) -> None:
    invoked: list[tuple[str, dict]] = []

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked.append((skill_id, params))
        if skill_id == "author_equipment_geometry" and "provided_inputs" not in params:
            return {
                "skill_id": skill_id,
                "input_required": {
                    "missing_inputs": [
                        {
                            "name": "rod_diameter",
                            "description": "Outer diameter of the actuator shaft, in metres.",
                            "user_prompt": "Rod diameter (m)",
                            "type": "number",
                            "options": None,
                            "resolvable_from_context": True,
                            "sensitive": False,
                            "required": True,
                        },
                    ],
                    "hint": "Butterfly valve dimensions required",
                },
                "_a2a_context_id": "conv-1",
                "_a2a_task_id": "task-1",
            }
        return {"skill_id": skill_id, "result": {"status": "completed"}}

    async def fake_get_capability_by_skill_id(skill_id):
        return None

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_by_skill_id=lambda skill_id: None,
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "author_equipment_geometry",
            "supporting_skills": ["mesh_geometry"],
            "workflow_type": "sequential",
            "extracted_params": {},
        },
        "context": {"rod_diameter": 0.05},
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert [skill_id for skill_id, _ in invoked] == [
        "author_equipment_geometry",
        "author_equipment_geometry",
        "mesh_geometry",
    ]
    assert invoked[1][1]["provided_inputs"] == {"rod_diameter": 0.05}
    assert result.get("missing_info", []) == []
    assert result["tool_results"]["mesh_geometry"] == {"status": "completed"}


def test_sequential_execution_overrides_stale_planning_time_artifact_binding(monkeypatch) -> None:
    """Regression: 'revise the valve, then mesh it' meshed the ORIGINAL valve.
    Planning-time artifact resolution correctly bound the existing valve for
    step 1 (revise), but the shared params dict leaked that binding into step
    2 (mesh), and already-filled refs were not overridden with the chain's
    own output."""
    captured_params: dict = {}

    revise_schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "x_artifact_ref": "single"},
            "instructions": {"type": "string"},
        },
        "required": ["artifact_id", "instructions"],
    }
    mesh_schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "x_artifact_ref": "single"},
            "element_type": {"type": "string"},
        },
        "required": ["artifact_id"],
    }
    schemas = {"revise_model": revise_schema, "mesh_model": mesh_schema}
    resolver_contexts: dict[str, dict] = {}

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        captured_params[skill_id] = params
        if skill_id == "revise_model":
            return {
                "skill_id": skill_id,
                "result": {
                    "status": "success",
                    "artifacts": [
                        {"artifact_id": "valve-revised", "name": "valve_rev2.step"},
                        {"artifact_id": "revision-report", "name": "changes.json"},
                    ],
                },
            }
        return {"skill_id": skill_id, "result": {"status": "success"}}

    async def fake_get_capability_by_skill_id(skill_id):
        schema = schemas.get(skill_id)
        return (
            SimpleNamespace(skill_id=skill_id, input_schema=schema, provides=None)
            if schema
            else None
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        skill_id = kwargs["capabilities"][0].skill_id
        resolver_contexts[skill_id] = kwargs["context"]
        assert kwargs["query"] == "Mesh the revised valve."
        return {"artifact_id": "valve-revised", "element_type": "tet"}

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
            get_by_skill_id=lambda skill_id: None,
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "routing_decision": {
            "primary_skill": "revise_model",
            "supporting_skills": ["mesh_model"],
            "workflow_type": "sequential",
            # Planning-time resolution bound the EXISTING valve (right for step 1).
            "extracted_params": {
                "artifact_id": "valve-original",
                "instructions": "reduce to 8 holes, five times larger",
                "element_type": "tet",
            },
            "capability_params": {
                "revise_model": {
                    "artifact_id": "valve-original",
                    "instructions": "reduce to 8 holes, five times larger",
                },
                "mesh_model": {
                    "artifact_id": "valve-original",
                    "element_type": "tet",
                },
            },
            "operations": [
                {
                    "operation_id": "op_1",
                    "description": "Revise the valve.",
                    "depends_on": [],
                },
                {
                    "operation_id": "op_2",
                    "description": "Mesh the revised valve.",
                    "depends_on": ["op_1"],
                },
            ],
            "operation_coverage": {
                "op_1": "revise_model",
                "op_2": "mesh_model",
            },
        },
        "context": {
            "artifacts": [
                {"artifact_id": "valve-original", "name": "valve.step"}
            ]
        },
        "conversation_history": [],
    }

    asyncio.run(agent_module.invoke_agent_generic(state))

    # Step 1 revised the original valve...
    assert captured_params["revise_model"]["artifact_id"] == "valve-original"
    # ...and step 2 meshed the chain's own output — the revised model, not the
    # inherited original and not the side-artifact report.
    assert captured_params["mesh_model"]["artifact_id"] == "valve-revised"
    assert [
        artifact["artifact_id"]
        for artifact in resolver_contexts["mesh_model"]["artifacts"]
    ] == [
        "valve-original",
        "valve-revised",
        "revision-report",
    ]
    assert resolver_contexts["mesh_model"]["_operation_dependencies"] == {
        "revise_model": ["valve-revised", "revision-report"]
    }


def test_sequential_execution_uses_step_local_params_and_dependency_context(
    monkeypatch,
) -> None:
    invoked: dict[str, dict] = {}
    resolver_calls: list[dict] = []

    author_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    mesh_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "cad_artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
            },
            "reference_artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
            },
        },
        "required": ["message", "cad_artifact_id", "reference_artifact_id"],
    }
    schemas = {
        "author_equipment_geometry": author_schema,
        "mesh_geometry": mesh_schema,
    }

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked[skill_id] = dict(params)
        if skill_id == "author_equipment_geometry":
            return {
                "skill_id": skill_id,
                "result": {
                    "message": "Authored updated valve.",
                    "artifacts": [
                        {
                            "artifact_id": "new-step",
                            "name": "updated.step",
                            "mime_type": "application/step",
                        }
                    ],
                },
            }
        return {"skill_id": skill_id, "result": {"status": "completed"}}

    async def fake_get_capability_by_skill_id(skill_id):
        return SimpleNamespace(
            skill_id=skill_id,
            input_schema=schemas[skill_id],
            provides=None,
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        resolver_calls.append(kwargs)
        skill_id = kwargs["capabilities"][0].skill_id
        assert kwargs["query"] == "Mesh the newly authored valve."
        assert kwargs["existing_params"] == {
            "message": "Use the prior mesh settings.", "reference_artifact_id": "old-step"
        }
        assert kwargs["history"][-1]["content"] == "Authored updated valve."
        assert kwargs["history"][-1]["tool_results"][
            "author_equipment_geometry"
        ]["artifacts"][0]["artifact_id"] == "new-step"
        assert [
            artifact["artifact_id"]
            for artifact in kwargs["context"]["artifacts"]
        ] == ["old-step", "new-step"]
        assert kwargs["context"]["_operation_dependencies"] == {
            "author_equipment_geometry": ["new-step"]
        }
        return {
            "message": "Mesh the STEP produced by the authoring step.",
            "cad_artifact_id": "new-step",
            "reference_artifact_id": "old-step",
        }

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
            get_by_skill_id=lambda skill_id: None,
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "user_query": "Make the holes larger, then mesh the updated valve.",
        "routing_decision": {
            "primary_skill": "author_equipment_geometry",
            "supporting_skills": ["mesh_geometry"],
            "workflow_type": "sequential",
            "extracted_params": {
                "message": "Re-author the valve with larger holes.",
                "cad_artifact_id": "old-step",
            },
            "capability_params": {
                "author_equipment_geometry": {
                    "message": "stale authoring snapshot"
                },
                "mesh_geometry": {
                    "message": "stale current planning params",
                    "cad_artifact_id": "old-step",
                },
            },
            "operations": [
                {
                    "operation_id": "op_1",
                    "description": "Re-author the valve with larger holes.",
                    "depends_on": [],
                },
                {
                    "operation_id": "op_2",
                    "description": "Mesh the newly authored valve.",
                    "depends_on": ["op_1"],
                },
            ],
            "operation_coverage": {
                "op_1": "author_equipment_geometry",
                "op_2": "mesh_geometry",
            },
        },
        "context": {
            "artifacts": [
                {"artifact_id": "old-step", "name": "old-valve.step"}
            ]
        },
        "prior_capability_params": {
            "mesh_geometry": {
                "message": "Use the prior mesh settings.",
                "reference_artifact_id": "old-step",
            }
        },
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert invoked["author_equipment_geometry"]["message"] == (
        "Re-author the valve with larger holes."
    )
    assert invoked["mesh_geometry"]["message"] == (
        "Mesh the STEP produced by the authoring step."
    )
    assert invoked["mesh_geometry"]["cad_artifact_id"] == "new-step"
    assert invoked["mesh_geometry"]["reference_artifact_id"] == "old-step"
    assert len(resolver_calls) == 1
    assert result["conversation_history"][-1]["tool_inputs"] == {
        "author_equipment_geometry": {
            "message": "Re-author the valve with larger holes."
        },
        "mesh_geometry": {
            "message": "Mesh the STEP produced by the authoring step.",
            "cad_artifact_id": "new-step",
            "reference_artifact_id": "old-step",
        },
    }


def test_sequential_execution_uses_text_only_step_result_for_next_inputs(
    monkeypatch,
) -> None:
    """A downstream step can infer inputs from an agent's chat contribution."""
    invoked: dict[str, dict] = {}

    schemas = {
        "search_literature": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "configure_analysis": {
            "type": "object",
            "properties": {"element_size_mm": {"type": "number"}},
            "required": ["element_size_mm"],
        },
    }

    async def fake_invoke_skill(skill_id, params, conversation_id, emit_status=True):
        invoked[skill_id] = dict(params)
        if skill_id == "search_literature":
            return {
                "skill_id": skill_id,
                "result": {
                    "answer": "The literature recommends 2 mm elements.",
                    "citations": ["paper-1"],
                },
            }
        return {"skill_id": skill_id, "result": {"status": "configured"}}

    async def fake_get_capability_by_skill_id(skill_id):
        return SimpleNamespace(
            skill_id=skill_id,
            input_schema=schemas[skill_id],
            provides=None,
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        skill_id = kwargs["capabilities"][0].skill_id
        prior_turn = kwargs["history"][-1]
        assert prior_turn["content"] == "The literature recommends 2 mm elements."
        assert prior_turn["tool_results"]["search_literature"]["citations"] == [
            "paper-1"
        ]
        assert kwargs["context"].get("artifacts") is None
        assert kwargs["context"]["_operation_dependencies"] == {
            "search_literature": []
        }
        return {"element_size_mm": 2.0}

    monkeypatch.setattr(agent_module, "invoke_skill", fake_invoke_skill)
    monkeypatch.setattr(
        agent_module._execution,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_module,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id,
            get_by_skill_id=lambda skill_id: None,
        ),
    )

    state = {
        "conversation_id": "conv-1",
        "user_query": "Find a recommended element size and configure the analysis.",
        "routing_decision": {
            "primary_skill": "search_literature",
            "supporting_skills": ["configure_analysis"],
            "workflow_type": "sequential",
            "extracted_params": {"query": "recommended mesh element size"},
            "capability_params": {
                "search_literature": {
                    "query": "recommended mesh element size"
                }
            },
            "operations": [
                {
                    "operation_id": "op_1",
                    "description": "Find a recommended mesh element size.",
                    "depends_on": [],
                },
                {
                    "operation_id": "op_2",
                    "description": "Configure the analysis from the recommendation.",
                    "depends_on": ["op_1"],
                },
            ],
            "operation_coverage": {
                "op_1": "search_literature",
                "op_2": "configure_analysis",
            },
        },
        "context": {},
        "conversation_history": [],
    }

    result = asyncio.run(agent_module.invoke_agent_generic(state))

    assert invoked["configure_analysis"]["element_size_mm"] == 2.0
    assert result["tool_results"]["configure_analysis"] == {"status": "configured"}
