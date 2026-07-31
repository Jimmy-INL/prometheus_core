"""Tests for orchestrator.planning_flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import planner  # noqa: E402
from orchestrator import parameters, planning_flow  # noqa: E402


def test_extract_refinement_param_updates_resolves_nested_paths(monkeypatch) -> None:
    """Regression: get_nested_value was used without being imported, so any
    refinement instruction crashed chat() with a NameError once the LLM
    returned a parseable update payload."""

    capability = SimpleNamespace(
        input_schema={
            "type": "object",
            "properties": {
                "material_id": {"type": "string", "description": "Material identifier"},
                "context": {
                    "type": "object",
                    "properties": {
                        "temperature_c": {
                            "type": "number",
                            "description": "Operating temperature in Celsius",
                        }
                    },
                },
            },
            "required": ["material_id"],
        }
    )

    async def fake_get_capability_by_skill_id(skill_id):
        return capability

    fake_cache = SimpleNamespace(get_capability_by_skill_id=fake_get_capability_by_skill_id)
    monkeypatch.setattr(planning_flow, "get_capability_cache", lambda: fake_cache)
    # Schema properties are gathered via the shared parameters helper.
    monkeypatch.setattr(parameters, "get_capability_cache", lambda: fake_cache)

    class _FakeLLM:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def medium(self, messages, **kwargs):
            return SimpleNamespace(
                text='{"context": {"temperature_c": 400}, "material_id": ""}'
            )

    monkeypatch.setattr(planning_flow.runtime, "create_llm", lambda: _FakeLLM())

    routing_decision = {
        "primary_skill": "analyze_thermal",
        "supporting_skills": [],
        "workflow_type": "single",
        "extracted_params": {"material_id": "SS316", "context": {"temperature_c": 350}},
    }

    updates = asyncio.run(
        planning_flow.extract_refinement_param_updates(
            "actually use 400 degrees",
            routing_decision,
            conversation_history=[{"role": "user", "content": "thermal analysis of SS316"}],
        )
    )

    # The nested dotted path is resolved from the LLM's JSON (this line is the
    # one that raised NameError before the fix); empty strings are dropped.
    assert updates == {"context.temperature_c": 400}


def test_compile_query_plan_populates_missing_info_for_incomplete_plan(monkeypatch) -> None:
    corrosion_schema = {
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
    capability = SimpleNamespace(
        skill_id="analyze_corrosion",
        skill_name="Analyze Corrosion",
        description="Analyze corrosion in high-temperature water.",
        input_schema=corrosion_schema,
        requires_approval=True,
        agent_url="http://litellm:4000/a2a/corrosion-analysis-agent",
        expected_duration_seconds=5,
        provides=[],
    )

    async def fake_get_capabilities():
        return [capability]

    async def fake_compile_plan_with_tools(**kwargs):
        return planner.PlanningResult(
            outcome="agent_plan",
            primary_skill="analyze_corrosion",
            workflow_type="single",
            confidence=0.95,
            reasoning="Analyze corrosion risk in high-temperature water.",
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        assert kwargs["capabilities"] == [capability]
        return {
                "material_id": "SS316",
                "context": {"temperature_c": 300},
        }

    async def keep_extracted_params(
        query,
        extracted_params,
        selected_skills,
        context,
        conversation_history,
    ):
        return extracted_params

    monkeypatch.setattr(
        planning_flow,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        planning_flow,
        "compile_plan_with_tools",
        fake_compile_plan_with_tools,
    )
    monkeypatch.setattr(
        planning_flow,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(
        planning_flow,
        "resolve_params_via_capability_metadata",
        keep_extracted_params,
    )
    monkeypatch.setattr(
        planning_flow.runtime,
        "store_status_update",
        lambda *args, **kwargs: None,
    )

    result = asyncio.run(
        planning_flow.compile_query_plan(
            {
                "conversation_id": "conv-corrosion",
                "user_query": (
                    "Analyze corrosion risk for SS316 in a high-temperature "
                    "water environment at 300 C."
                ),
                "conversation_history": [],
                "context": {},
            }
        )
    )

    assert result["is_fallback"] is False
    assert result["routing_decision"]["primary_skill"] == "analyze_corrosion"
    assert result["routing_decision"]["missing_required_params"] == [
        "context.pressure_mpa"
    ]
    assert result["missing_info"] == ["context.pressure_mpa"]
    assert result["plan"]["skills"] == ["analyze_corrosion"]


def test_compile_query_plan_extracts_nested_bim_params_before_missing_form(
    monkeypatch,
) -> None:
    capability = SimpleNamespace(
        skill_id="author_equipment_geometry",
        skill_name="Author Equipment Geometry",
        description="Create parameterized equipment geometry.",
        input_schema={
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "object",
                    "properties": {
                        "equipment_type": {
                            "type": "string",
                            "enum": ["butterfly_valve"],
                        },
                        "pipe_diameter": {"type": "number"},
                        "num_holes": {"type": "integer"},
                        "hole_diameter": {"type": "number"},
                        "rod_diameter": {"type": "number"},
                    },
                    "required": [
                        "equipment_type",
                        "pipe_diameter",
                        "num_holes",
                        "hole_diameter",
                        "rod_diameter",
                    ],
                }
            },
            "required": ["input_data"],
        },
        requires_approval=False,
        agent_url="http://bim-agent:8000",
        expected_duration_seconds=10,
        provides=[],
    )

    async def fake_get_capabilities():
        return [capability]

    async def fake_compile_plan_with_tools(**kwargs):
        return planner.PlanningResult(
            outcome="agent_plan",
            primary_skill="author_equipment_geometry",
            workflow_type="single",
            confidence=0.95,
            reasoning="Create the requested butterfly valve.",
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        assert kwargs["capabilities"] == [capability]
        return {
            "input_data": {
                "equipment_type": "butterfly_valve",
                "pipe_diameter": 0.9,
                "num_holes": 6,
                "hole_diameter": 0.05,
            }
        }

    async def keep_extracted_params(
        query,
        extracted_params,
        selected_skills,
        context,
        conversation_history,
    ):
        return extracted_params

    monkeypatch.setattr(
        planning_flow,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        planning_flow,
        "compile_plan_with_tools",
        fake_compile_plan_with_tools,
    )
    monkeypatch.setattr(
        planning_flow,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(
        planning_flow,
        "resolve_params_via_capability_metadata",
        keep_extracted_params,
    )
    monkeypatch.setattr(
        planning_flow.runtime,
        "store_status_update",
        lambda *args, **kwargs: None,
    )

    result = asyncio.run(
        planning_flow.compile_query_plan(
            {
                "conversation_id": "conv-bim",
                "user_query": (
                    "Create a butterfly valve for a pipe diameter of 0.9m and "
                    "6 holes with a 5cm diameter each."
                ),
                "conversation_history": [],
                "context": {},
            }
        )
    )

    assert result["routing_decision"]["extracted_params"] == {
        "input_data": {
            "equipment_type": "butterfly_valve",
            "pipe_diameter": 0.9,
            "num_holes": 6,
            "hole_diameter": 0.05,
        }
    }
    assert result["missing_info"] == ["input_data.rod_diameter"]


def test_compile_query_plan_blocks_all_execution_for_unsupported_operation(
    monkeypatch,
) -> None:
    capability = SimpleNamespace(
        skill_id="convert_svg_to_png",
        skill_name="Convert SVG",
        description="Convert SVG to PNG.",
        input_schema={"type": "object", "properties": {}},
        requires_approval=False,
        agent_url="http://artifact-agent:8000",
        expected_duration_seconds=5,
        provides=[],
    )

    async def fake_get_capabilities():
        return [capability]

    async def fake_compile_plan_with_tools(**kwargs):
        return planner.PlanningResult(
            outcome="unsupported",
            operations=[
                planner.RequestedOperation(
                    operation_id="op_1",
                    description="Create CAD geometry for a butterfly valve",
                ),
                planner.RequestedOperation(
                    operation_id="op_2",
                    description="Mesh the CAD with tetrahedral elements",
                    depends_on=["op_1"],
                ),
            ],
            unsupported_operations=[
                planner.UnsupportedOperationInput(
                    operation_id="op_1",
                    reason="No CAD authoring capability is registered",
                ),
                planner.UnsupportedOperationInput(
                    operation_id="op_2",
                    reason="No meshing capability is registered",
                ),
            ],
        )

    async def extraction_must_not_run(**kwargs):
        raise AssertionError("Unsupported requests must not reach parameter extraction")

    monkeypatch.setattr(
        planning_flow,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        planning_flow,
        "compile_plan_with_tools",
        fake_compile_plan_with_tools,
    )
    monkeypatch.setattr(
        planning_flow,
        "extract_parameters_with_schemas",
        extraction_must_not_run,
    )
    monkeypatch.setattr(
        planning_flow.runtime,
        "store_status_update",
        lambda *args, **kwargs: None,
    )

    result = asyncio.run(
        planning_flow.compile_query_plan(
            {
                "conversation_id": "conv-unsupported",
                "user_query": "Create a CAD valve, then mesh it.",
                "conversation_history": [],
                "context": {},
            }
        )
    )

    assert result["is_fallback"] is True
    assert "Create CAD geometry for a butterfly valve" in result["fallback_message"]
    assert "Mesh the CAD with tetrahedral elements" in result["fallback_message"]


def test_followup_reauthors_geometry_from_prior_parameters_before_meshing(
    monkeypatch,
) -> None:
    author = SimpleNamespace(
        skill_id="author_equipment_geometry",
        skill_name="Author Equipment Geometry",
        description="Create parameterized equipment geometry.",
        input_schema={
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "object",
                    "properties": {
                        "equipment_type": {"type": "string"},
                        "pipe_diameter": {"type": "number"},
                        "num_holes": {"type": "integer"},
                        "hole_diameter": {"type": "number"},
                        "rod_diameter": {"type": "number"},
                    },
                    "required": [
                        "equipment_type",
                        "pipe_diameter",
                        "num_holes",
                        "hole_diameter",
                        "rod_diameter",
                    ],
                }
            },
            "required": ["input_data"],
        },
        requires_approval=False,
        agent_url="http://bim-agent:8000",
        expected_duration_seconds=10,
        provides=[],
    )
    mesh = SimpleNamespace(
        skill_id="mesh_geometry",
        skill_name="Mesh Geometry",
        description="Mesh a CAD artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "cad_artifact_id": {
                    "type": "string",
                    "x_artifact_ref": "single",
                },
            },
            "required": ["message", "cad_artifact_id"],
        },
        requires_approval=False,
        agent_url="http://mesh-agent:8000",
        expected_duration_seconds=120,
        provides=[],
    )
    prior = {
        "author_equipment_geometry": {
            "input_data": {
                "equipment_type": "butterfly_valve",
                "pipe_diameter": 0.9,
                "num_holes": 6,
                "hole_diameter": 0.05,
                "rod_diameter": 0.08,
            }
        }
    }

    async def fake_get_capabilities():
        return [author, mesh]

    async def fake_compile_plan_with_tools(**kwargs):
        assert kwargs["context"]["prior_capability_params"] == prior
        return planner.PlanningResult(
            outcome="agent_plan",
            primary_skill="author_equipment_geometry",
            supporting_skills=["mesh_geometry"],
            workflow_type="sequential",
            confidence=0.98,
            reasoning="Re-author the valve, then mesh the new CAD.",
        )

    async def fake_extract_parameters_with_schemas(**kwargs):
        assert kwargs["capabilities"] == [author, mesh]
        assert kwargs["context"]["prior_capability_params"] == prior
        assert kwargs["existing_params"] == {}
        return {
            "input_data": {
                "equipment_type": "butterfly_valve",
                "pipe_diameter": 0.9,
                "num_holes": 6,
                "hole_diameter": 0.10,
                "rod_diameter": 0.08,
            },
            "message": "Generate about 30000 tetrahedral elements.",
        }

    async def keep_extracted_params(**kwargs):
        return kwargs["extracted_params"]

    monkeypatch.setattr(
        planning_flow,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        planning_flow,
        "compile_plan_with_tools",
        fake_compile_plan_with_tools,
    )
    monkeypatch.setattr(
        planning_flow,
        "extract_parameters_with_schemas",
        fake_extract_parameters_with_schemas,
    )
    monkeypatch.setattr(
        planning_flow,
        "resolve_params_via_capability_metadata",
        keep_extracted_params,
    )
    monkeypatch.setattr(
        planning_flow.runtime,
        "store_status_update",
        lambda *args, **kwargs: None,
    )

    result = asyncio.run(
        planning_flow.compile_query_plan(
            {
                "conversation_id": "conv-valve-followup",
                "user_query": (
                    "Make the holes more evenly distributed and double their diameter, "
                    "then mesh the CAD with about 30000 tet elements."
                ),
                "conversation_history": [],
                "context": {"artifacts": [{"artifact_id": "old-step"}]},
                "prior_capability_params": prior,
            }
        )
    )

    routing = result["routing_decision"]
    assert routing["primary_skill"] == "author_equipment_geometry"
    assert routing["supporting_skills"] == ["mesh_geometry"]
    assert routing["workflow_type"] == "sequential"
    assert routing["extracted_params"]["input_data"] == {
        "equipment_type": "butterfly_valve",
        "pipe_diameter": 0.9,
        "num_holes": 6,
        "hole_diameter": 0.10,
        "rod_diameter": 0.08,
    }
    assert result["missing_info"] == []
    assert "prior_capability_params" not in result["context"]
