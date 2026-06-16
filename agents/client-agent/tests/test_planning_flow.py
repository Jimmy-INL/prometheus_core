"""Tests for orchestrator.planning_flow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from orchestrator import planning_flow  # noqa: E402


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

    class _FakeLLM:
        def invoke(self, messages):
            return SimpleNamespace(
                content='{"context": {"temperature_c": 400}, "material_id": ""}'
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
