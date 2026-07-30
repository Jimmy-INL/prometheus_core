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
            extracted_params={
                "material_id": "SS316",
                "context": {"temperature_c": 300},
            },
        )

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
