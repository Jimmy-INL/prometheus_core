"""Targeted tests for orchestrator execution-path selection."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
import types

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))
PROMETHEUS_API_DIR = Path(__file__).resolve().parents[3] / "prometheus_api"
if str(PROMETHEUS_API_DIR) not in sys.path:
    sys.path.insert(0, str(PROMETHEUS_API_DIR))

if "langchain_anthropic" not in sys.modules:
    langchain_anthropic = types.ModuleType("langchain_anthropic")
    langchain_anthropic.ChatAnthropic = object
    sys.modules["langchain_anthropic"] = langchain_anthropic

if "langchain_core.messages" not in sys.modules:
    langchain_core = sys.modules.setdefault("langchain_core", types.ModuleType("langchain_core"))
    messages_module = types.ModuleType("langchain_core.messages")
    messages_module.HumanMessage = object
    messages_module.SystemMessage = object
    messages_module.ToolMessage = object
    sys.modules["langchain_core.messages"] = messages_module
    langchain_core.messages = messages_module

if "langchain_core.tools" not in sys.modules:
    tools_module = types.ModuleType("langchain_core.tools")

    class _StructuredTool:
        @staticmethod
        def from_function(*args, **kwargs):
            return SimpleNamespace(name=kwargs.get("name", "tool"), invoke=lambda tool_args: {})

    tools_module.StructuredTool = _StructuredTool
    sys.modules["langchain_core.tools"] = tools_module

import agent as agent_module


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


def test_chat_asks_followup_when_required_params_are_missing_on_initial_turn(monkeypatch) -> None:
    async def fake_compile_query_plan(state, **kwargs):
        return {
            "routing_decision": {
                "primary_skill": "analyze_thermal",
                "supporting_skills": [],
                "workflow_type": "single",
                "extracted_params": {"material_id": "SS316"},
                "requires_approval": True,
                "required_params": ["material_id", "context.temperature_c"],
                "missing_required_params": ["context.temperature_c"],
            },
            "plan": {
                "intent": "Perform a thermal analysis of ss316",
                "workflow_type": "single",
                "skills": ["analyze_thermal"],
                "required_params": ["material_id", "context.temperature_c"],
                "steps": ["Invoke analyze_thermal"],
                "missing_info": ["context.temperature_c"],
                "estimated_duration_seconds": 5,
                "param_metadata": {},
            },
            "missing_info": ["context.temperature_c"],
            "context": {},
            "material_id": "SS316",
        }

    async def fake_ask_followup_dynamic(state):
        return {
            "conversation_history": state.get("conversation_history", []) + [
                {
                    "role": "assistant",
                    "type": "followup_questions",
                    "questions": [
                        {
                            "field": "context.temperature_c",
                            "question": "Operating temperature in Celsius",
                            "type": "number",
                        }
                    ],
                }
            ],
            "missing_info": ["context.temperature_c"],
            "awaiting_approval": False,
        }

    async def should_not_extract(*args, **kwargs):
        raise AssertionError("Initial turn should not auto-extract missing follow-up answers from the query.")

    monkeypatch.setattr(agent_module, "compile_query_plan", fake_compile_query_plan)
    monkeypatch.setattr(agent_module, "ask_followup_dynamic", fake_ask_followup_dynamic)
    monkeypatch.setattr(agent_module, "extract_followup_answers_from_query", should_not_extract)
    monkeypatch.setattr(agent_module, "get_conversation", lambda conversation_id: None)
    monkeypatch.setattr(agent_module, "store_conversation", lambda conversation_id, state: None)
    monkeypatch.setattr(agent_module, "store_status_update", lambda *args, **kwargs: None)

    response = asyncio.run(
        agent_module.chat(
            agent_module.ConversationRequest(
                query="Perform a thermal analysis of ss316",
                conversation_id="conv-1",
            )
        )
    )

    assert response.status == "needs_info"
    assert response.followup_questions == [
        {
            "field": "context.temperature_c",
            "question": "Operating temperature in Celsius",
            "type": "number",
        }
    ]


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
        "pending_subagent_request": {
            "skill_id": "analyze_thermal",
            "missing_inputs": [
                {
                    "name": "temperature_c",
                    "description": "Operating temperature in Celsius at which the material should be evaluated.",
                    "user_prompt": "What operating temperature should I use for the thermal analysis (in Celsius)?",
                    "type": "number",
                    "resolvable_from_context": True,
                }
            ],
            "hint": "Thermal analysis requires an operating temperature before it can proceed.",
        },
    }

    result = asyncio.run(agent_module.ask_followup_dynamic(state))

    question = result["conversation_history"][-1]["questions"][0]
    assert question["field"] == "temperature_c"
    assert question["type"] == "number"
    assert result["missing_info"] == ["temperature_c"]
