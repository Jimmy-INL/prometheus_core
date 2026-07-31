"""Tests for strict request decomposition and exhaustive operation coverage."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import planner  # noqa: E402
from capability_cache import AgentCapability  # noqa: E402
from orchestrator import parameters, runtime  # noqa: E402


def _operation(operation_id: str, description: str, depends_on=None):
    return planner.RequestedOperation(
        operation_id=operation_id,
        description=description,
        depends_on=list(depends_on or []),
    )


CAPABILITIES = {
    "author_equipment_geometry": SimpleNamespace(input_schema={}),
    "mesh_geometry": SimpleNamespace(input_schema={}),
}


def _tools_by_name(draft):
    tools = planner._build_planning_tools(draft, CAPABILITIES, context={})
    return {tool.name: tool.func for tool in tools}


def test_mesh_only_plan_cannot_finalize_when_geometry_update_is_uncovered() -> None:
    draft = planner._PlanDraft(
        operations=[
            _operation("op_1", "Re-author the valve with larger, evenly distributed holes"),
            _operation("op_2", "Mesh the newly authored CAD with tetrahedra", ["op_1"]),
        ]
    )
    tools = _tools_by_name(draft)

    tools["select_capabilities"](
        primary_skill="mesh_geometry",
        workflow_type="single",
    )
    tools["set_operation_coverage"](
        covered=[{"operation_id": "op_2", "skill_id": "mesh_geometry"}],
        unsupported=[],
    )

    result = tools["finalize_plan"]()

    assert result["ok"] is False
    assert result["uncovered_operation_ids"] == ["op_1"]
    assert draft.finalized is False


def test_reauthor_then_mesh_plan_finalizes_in_dependency_order() -> None:
    draft = planner._PlanDraft(
        operations=[
            _operation("op_1", "Re-author the valve with larger, evenly distributed holes"),
            _operation("op_2", "Mesh the newly authored CAD with tetrahedra", ["op_1"]),
        ]
    )
    tools = _tools_by_name(draft)

    tools["select_capabilities"](
        primary_skill="author_equipment_geometry",
        supporting_skills=["mesh_geometry"],
        workflow_type="sequential",
    )
    coverage = tools["set_operation_coverage"](
        covered=[
            {"operation_id": "op_1", "skill_id": "author_equipment_geometry"},
            {"operation_id": "op_2", "skill_id": "mesh_geometry"},
        ],
        unsupported=[],
    )

    assert coverage["ok"] is True
    assert tools["finalize_plan"]()["ok"] is True
    assert draft.finalized is True


def test_cross_skill_dependency_requires_sequential_selection_order() -> None:
    draft = planner._PlanDraft(
        operations=[
            _operation("op_1", "Re-author the valve"),
            _operation("op_2", "Mesh the new CAD", ["op_1"]),
        ]
    )
    tools = _tools_by_name(draft)

    tools["select_capabilities"](
        primary_skill="mesh_geometry",
        supporting_skills=["author_equipment_geometry"],
        workflow_type="sequential",
    )
    tools["set_operation_coverage"](
        covered=[
            {"operation_id": "op_1", "skill_id": "author_equipment_geometry"},
            {"operation_id": "op_2", "skill_id": "mesh_geometry"},
        ],
        unsupported=[],
    )

    result = tools["finalize_plan"]()

    assert result["ok"] is False
    assert "dependency order" in result["error"]


def test_execution_preserves_validated_operation_dependency_order(monkeypatch) -> None:
    monkeypatch.setattr(
        parameters,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_by_skill_id=lambda skill_id: SimpleNamespace(
                usage_notes="",
                provides=[],
                derivation_rules=[],
                execution_priority=(
                    "late" if skill_id == "author_equipment_geometry" else "early"
                ),
            )
        ),
    )
    routing = {
        "primary_skill": "author_equipment_geometry",
        "supporting_skills": ["mesh_geometry"],
        "workflow_type": "sequential",
        "operations": [
            {"operation_id": "op_1", "depends_on": []},
            {"operation_id": "op_2", "depends_on": ["op_1"]},
        ],
        "operation_coverage": {
            "op_1": "author_equipment_geometry",
            "op_2": "mesh_geometry",
        },
    }

    assert parameters.order_skills_for_workflow(routing) == [
        "author_equipment_geometry",
        "mesh_geometry",
    ]


def test_any_unsupported_operation_blocks_partial_execution() -> None:
    draft = planner._PlanDraft(
        operations=[
            _operation("op_1", "Create CAD geometry"),
            _operation("op_2", "Mesh the CAD", ["op_1"]),
        ]
    )
    tools = _tools_by_name(draft)

    tools["select_capabilities"](
        primary_skill="mesh_geometry",
        workflow_type="single",
    )
    tools["set_operation_coverage"](
        covered=[{"operation_id": "op_2", "skill_id": "mesh_geometry"}],
        unsupported=[{"operation_id": "op_1", "reason": "No CAD author is registered"}],
    )

    result = tools["finalize_plan"]()

    assert result["ok"] is True
    assert draft.outcome == "unsupported"
    assert draft.primary_skill is None
    assert draft.finalized is True


def test_no_registered_capabilities_marks_every_operation_unsupported() -> None:
    result = asyncio.run(
        planner.compile_plan_with_tools(
            query="Create CAD and mesh it.",
            capabilities=[],
            operations=[
                _operation("op_1", "Create CAD geometry"),
                _operation("op_2", "Mesh the CAD", ["op_1"]),
            ],
        )
    )

    assert result.outcome == "unsupported"
    assert [item.operation_id for item in result.unsupported_operations] == [
        "op_1",
        "op_2",
    ]


class _DecompositionLLM:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def medium(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return SimpleNamespace(
            raw={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": self.tool_calls,
                        }
                    }
                ]
            }
        )


def _decomposition_call(arguments, call_id="decompose-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "decompose_request",
            "arguments": json.dumps(arguments),
        },
    }


def test_decomposition_assigns_stable_ids_and_dependencies(monkeypatch) -> None:
    fake_llm = _DecompositionLLM(
        [
            _decomposition_call(
                {
                    "request_kind": "task",
                    "operations": [
                        {
                            "description": "Re-author the valve with twice the hole diameter",
                            "depends_on": [],
                        },
                        {
                            "description": "Mesh the newly authored CAD with about 30000 tetrahedra",
                            "depends_on": [1],
                        },
                    ],
                    "message": "",
                }
            )
        ]
    )
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    result = asyncio.run(
        planner.decompose_request(
            query="Make the holes larger, then mesh the CAD.",
            history=[],
            context={},
        )
    )

    assert [operation.operation_id for operation in result.operations] == ["op_1", "op_2"]
    assert result.operations[1].depends_on == ["op_1"]
    prompt = fake_llm.calls[0][0][1]["content"]
    assert "Available capabilities" not in prompt


def test_decomposition_rejects_more_than_one_tool_call(monkeypatch) -> None:
    arguments = {
        "request_kind": "task",
        "operations": [{"description": "Mesh CAD", "depends_on": []}],
        "message": "",
    }
    fake_llm = _DecompositionLLM(
        [_decomposition_call(arguments, "one"), _decomposition_call(arguments, "two")]
    )
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    with pytest.raises(planner.PlanningContractError, match="exactly once"):
        asyncio.run(
            planner.decompose_request(
                query="Mesh the CAD.",
                history=[],
                context={},
            )
        )


def test_unfinalized_planner_response_is_a_contract_error(monkeypatch) -> None:
    class _NoToolLLM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def medium(self, messages, **kwargs):
            return SimpleNamespace(
                raw={"choices": [{"message": {"content": "", "tool_calls": []}}]}
            )

    monkeypatch.setattr(runtime, "create_llm", lambda: _NoToolLLM())

    with pytest.raises(planner.PlanningContractError, match="did not finalize"):
        asyncio.run(
            planner.compile_plan_with_tools(
                query="Mesh the CAD.",
                capabilities=[
                    AgentCapability(
                        agent_id="mesh-agent",
                        agent_name="Mesh Agent",
                        agent_url="http://mesh-agent:8000",
                        skill_id="mesh_geometry",
                        skill_name="Mesh Geometry",
                        description="Mesh CAD geometry.",
                    )
                ],
                operations=[_operation("op_1", "Mesh the CAD")],
                max_turns=1,
            )
        )
