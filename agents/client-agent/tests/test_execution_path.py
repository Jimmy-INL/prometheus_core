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
