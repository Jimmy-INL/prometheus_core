"""Tests for sequential-dataflow handling in the planner's requirement checks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import planner  # noqa: E402
from workflow_library.naming import workflow_tool_name  # noqa: E402

CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "word": {"type": "string", "description": "Text to render"},
        "color": {"type": "string", "description": "Text color"},
    },
    "required": ["word"],
}

CONVERT_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_id": {
            "type": "string",
            "description": "Artifact ID of the SVG to convert.",
            "x_artifact_ref": "single",
        },
        "name": {"type": "string"},
    },
    "required": ["artifact_id"],
}

CORROSION_SCHEMA = {
    "type": "object",
    "properties": {
        "material_id": {
            "type": "string",
            "description": "The unique identifier of the material to analyze",
        },
        "context": {
            "type": "object",
            "properties": {
                "temperature_c": {
                    "type": "number",
                    "description": "Operating temperature in Celsius",
                },
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

RUNTIME_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "material_id": {"type": "string"},
        "tool_results": {
            "type": "object",
            "x_input_source": "runtime",
        },
    },
    "required": ["material_id", "tool_results"],
}

CAPABILITIES = {
    "create_svg_artifact": SimpleNamespace(input_schema=CREATE_SCHEMA),
    "convert_svg_to_png": SimpleNamespace(input_schema=CONVERT_SCHEMA),
}


def _tools_by_name(draft):
    tools = planner._build_planning_tools(draft, CAPABILITIES, context={})
    return {tool.name: tool.func for tool in tools}


def test_workflow_templates_are_registered_as_planner_tools():
    draft = planner._PlanDraft()
    candidate = planner.WorkflowPlanningCandidate(
        workflow_id="artifact_debug.patriotic_usa_png",
        workflow_version="1.0.0",
        score=0.0,
        skills=["create_svg_artifact", "convert_svg_to_png"],
        display_name="Patriotic USA PNG",
        summary="Create a patriotic image and convert it to PNG.",
        tool_name=workflow_tool_name("artifact_debug.patriotic_usa_png"),
    )
    tools = planner._build_planning_tools(
        draft,
        CAPABILITIES,
        context={},
        workflow_candidates=[candidate],
    )
    funcs = {tool.name: tool.func for tool in tools}

    result = funcs["workflow_artifact_debug_patriotic_usa_png"](
        reasoning="patriotic request",
        confidence=0.9,
    )

    assert result["ok"] is True
    assert draft.workflow_id == "artifact_debug.patriotic_usa_png"
    assert draft.workflow_type == "workflow_template"
    assert draft.primary_skill == "create_svg_artifact"
    assert draft.supporting_skills == ["convert_svg_to_png"]


def test_sequential_plan_defers_downstream_artifact_refs():
    """Regression: a chained request ("make an SVG, then convert it to PNG")
    could not be finalized because the converter's artifact_id is required but
    cannot exist until the first step runs — so the planner dropped the
    conversion step and only the SVG was created."""
    draft = planner._PlanDraft()
    tools = _tools_by_name(draft)

    selected = tools["select_capabilities"](
        primary_skill="create_svg_artifact",
        supporting_skills=["convert_svg_to_png"],
        workflow_type="sequential",
        reasoning="create then convert",
        confidence=0.9,
    )
    assert selected["ok"] is True

    tools["set_extracted_params"]({"word": "LBNL is a cool lab"})

    status = tools["get_requirement_status"]()
    # artifact_id is produced by step 1 at runtime: deferred, not missing.
    assert status["deferred_runtime_paths"] == ["artifact_id"]
    assert "artifact_id" not in status["missing_paths"]
    assert "artifact_id" not in status["unresolved_runtime_paths"]

    finalized = tools["finalize_plan"]()
    assert finalized["ok"] is True, finalized
    assert draft.primary_skill == "create_svg_artifact"
    assert draft.supporting_skills == ["convert_svg_to_png"]
    assert draft.workflow_type == "sequential"


def test_single_plan_preserves_missing_artifact_ref_for_followup():
    """A missing user-supplied artifact ref belongs in the incomplete plan."""
    draft = planner._PlanDraft()
    tools = _tools_by_name(draft)

    tools["select_capabilities"](
        primary_skill="convert_svg_to_png",
        workflow_type="single",
    )
    status = tools["get_requirement_status"]()
    assert "artifact_id" in status["missing_paths"]
    assert status["deferred_runtime_paths"] == []

    finalized = tools["finalize_plan"]()
    assert finalized == {
        "ok": True,
        "finalized": True,
        "missing_paths": ["artifact_id"],
    }
    assert draft.finalized is True


def test_plan_with_missing_user_fields_finalizes_for_followup_collection():
    draft = planner._PlanDraft()
    tools = planner._build_planning_tools(
        draft,
        {"analyze_corrosion": SimpleNamespace(input_schema=CORROSION_SCHEMA)},
        context={},
    )
    funcs = {tool.name: tool.func for tool in tools}

    funcs["select_capabilities"](
        primary_skill="analyze_corrosion",
        workflow_type="single",
        reasoning="Analyze corrosion risk in high-temperature water",
        confidence=0.95,
    )
    funcs["set_extracted_params"](
        {
            "material_id": "SS316",
            "context": {"temperature_c": 300},
        }
    )

    finalized = funcs["finalize_plan"]()

    assert finalized == {
        "ok": True,
        "finalized": True,
        "missing_paths": ["context.pressure_mpa"],
    }
    assert draft.primary_skill == "analyze_corrosion"
    assert draft.finalized is True


def test_plan_with_unresolved_runtime_field_still_cannot_finalize():
    draft = planner._PlanDraft()
    tools = planner._build_planning_tools(
        draft,
        {"synthesize": SimpleNamespace(input_schema=RUNTIME_INPUT_SCHEMA)},
        context={},
    )
    funcs = {tool.name: tool.func for tool in tools}

    funcs["select_capabilities"](
        primary_skill="synthesize",
        workflow_type="single",
    )
    funcs["set_extracted_params"]({"material_id": "SS316"})

    finalized = funcs["finalize_plan"]()

    assert finalized["ok"] is False
    assert finalized["unresolved_runtime_paths"] == ["tool_results"]
    assert draft.finalized is False


def test_compile_query_plan_does_not_ask_for_deferred_artifact_ids(monkeypatch):
    """Regression: after the planner correctly selected the sequential chain,
    compile_query_plan independently recomputed required params from all
    skill schemas and flagged the downstream artifact_id as missing — so the
    approved chain immediately bounced back to the user as an INPUT_REQUIRED
    form asking for an artifact id that does not exist yet."""
    import asyncio

    from orchestrator import planning_flow

    create_cap = SimpleNamespace(
        skill_id="create_svg_artifact",
        skill_name="Create SVG",
        name="Create SVG",
        description="Create an SVG image",
        input_schema=CREATE_SCHEMA,
        requires_approval=False,
        agent_url="http://artifact-debug-agent:8000",
        expected_duration_seconds=5,
        provides=None,
    )
    convert_cap = SimpleNamespace(
        skill_id="convert_svg_to_png",
        skill_name="Convert SVG to PNG",
        name="Convert SVG to PNG",
        description="Convert an SVG artifact to PNG",
        input_schema=CONVERT_SCHEMA,
        requires_approval=False,
        agent_url="http://artifact-debug-agent:8000",
        expected_duration_seconds=5,
        provides=None,
    )

    async def fake_get_capabilities():
        return [create_cap, convert_cap]

    fake_cache = SimpleNamespace(get_capabilities=fake_get_capabilities)
    monkeypatch.setattr(planning_flow, "get_capability_cache", lambda: fake_cache)
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        planning_flow.runtime, "store_status_update", lambda *args, **kwargs: None
    )

    async def fake_resolve_params(query, extracted_params, selected_skills, context, conversation_history):
        return extracted_params

    monkeypatch.setattr(
        planning_flow, "resolve_params_via_capability_metadata", fake_resolve_params
    )

    async def fake_compile_plan_with_tools(**kwargs):
        return planner.PlanningResult(
            outcome="agent_plan",
            primary_skill="create_svg_artifact",
            supporting_skills=["convert_svg_to_png"],
            workflow_type="sequential",
            extracted_params={"word": "LBNL is a cool lab"},
            reasoning="create then convert",
            confidence=0.9,
        )

    monkeypatch.setattr(planning_flow, "compile_plan_with_tools", fake_compile_plan_with_tools)

    state = {
        "conversation_id": "conv-1",
        "user_query": 'Make an image with "LBNL is a cool lab", then convert it to PNG.',
        "conversation_history": [],
        "context": {},
    }

    result = asyncio.run(planning_flow.compile_query_plan(state))

    routing = result["routing_decision"]
    assert routing["workflow_type"] == "sequential"
    assert routing["supporting_skills"] == ["convert_svg_to_png"]
    # The deferred artifact id must not trigger a follow-up form.
    assert "artifact_id" not in routing["missing_required_params"]
    assert "artifact_id" not in result.get("missing_info", [])


def test_compile_query_plan_does_not_auto_select_registered_workflow_on_fallback(monkeypatch):
    import asyncio

    from orchestrator import planning_flow

    create_cap = SimpleNamespace(
        skill_id="create_svg_artifact",
        skill_name="Create SVG",
        description="Create an SVG image",
        input_schema=CREATE_SCHEMA,
        requires_approval=False,
        agent_url="http://artifact-debug-agent:8000",
        expected_duration_seconds=5,
    )
    workflow = SimpleNamespace(
        required_input_paths=[],
        definition=SimpleNamespace(
            id="artifact_debug.patriotic_usa_png",
            version="1.0.0",
            name="Patriotic USA PNG",
            description="Create a patriotic image.",
            steps=[SimpleNamespace(skill_id="create_svg_artifact")],
            execution=SimpleNamespace(mode="sequential"),
            metadata=SimpleNamespace(estimated_duration_seconds=5),
            ui=SimpleNamespace(display_name="Patriotic USA PNG", summary="Create a patriotic image."),
        ),
    )

    async def fake_get_capabilities():
        return [create_cap]

    monkeypatch.setattr(
        planning_flow,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capabilities=fake_get_capabilities),
    )
    monkeypatch.setattr(planning_flow.runtime, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(
        planning_flow,
        "get_workflow_registry",
        lambda: SimpleNamespace(list_all=lambda: [workflow], get=lambda *args, **kwargs: workflow),
    )
    monkeypatch.setattr(
        planning_flow.runtime,
        "store_status_update",
        lambda *args, **kwargs: None,
    )

    async def fake_compile_plan_with_tools(**kwargs):
        assert kwargs["workflow_candidates"]
        return planner.PlanningResult(outcome="fallback", message="ask a question")

    monkeypatch.setattr(planning_flow, "compile_plan_with_tools", fake_compile_plan_with_tools)

    state = {
        "conversation_id": "conv-1",
        "user_query": "hello",
        "conversation_history": [],
        "context": {},
    }

    result = asyncio.run(planning_flow.compile_query_plan(state))

    assert result == {"is_fallback": True, "fallback_message": "ask a question"}
