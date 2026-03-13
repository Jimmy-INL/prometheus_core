"""Unit tests for workflow library compile/match/execute behavior."""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from workflow_library.compiler import WorkflowCompileError, compile_workflow
from workflow_library.executor import execute_workflow
from workflow_library.matcher import match_workflows
from workflow_library.registry import WorkflowRegistry


@dataclass
class _Capability:
    """Minimal capability shape required by workflow compiler/registry."""

    agent_id: str
    agent_name: str
    agent_url: str
    skill_id: str
    skill_name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


def _capability(skill_id: str, input_schema: Dict[str, Any] | None = None) -> _Capability:
    return _Capability(
        agent_id=f"{skill_id}-agent",
        agent_name=f"{skill_id} agent",
        agent_url=f"http://{skill_id}:8000",
        skill_id=skill_id,
        skill_name=skill_id,
        description=f"Skill {skill_id}",
        input_schema=input_schema or {"type": "object", "properties": {}, "required": []},
    )


def _compile(raw: Dict[str, Any]) -> Any:
    capabilities = {step["skill_id"]: _capability(step["skill_id"]) for step in raw.get("steps", [])}
    return compile_workflow(raw=raw, source_path=Path("test.yaml"), capabilities_by_skill=capabilities, strict=True)


def test_matcher_preserves_underscore_placeholders() -> None:
    workflow = _compile(
        {
            "id": "w1",
            "name": "W1",
            "version": "1.0.0",
            "description": "test",
            "matching": {"priority": 10, "patterns": ["full safety analysis of {material_id}"]},
            "inputs": {"required": ["material_id"]},
            "execution": {"mode": "sequential", "on_error": "fail_fast"},
            "steps": [{"id": "s1", "skill_id": "get_material_data"}],
        }
    )

    matches = match_workflows("Full safety analysis of SS316", [workflow])
    assert matches
    assert matches[0].extracted_params.get("material_id") == "SS316"
    assert "material.id" not in matches[0].extracted_params


def test_matcher_tie_break_is_deterministic_lexical_id() -> None:
    workflow_a = _compile(
        {
            "id": "alpha_workflow",
            "name": "Alpha",
            "version": "1.0.0",
            "description": "test",
            "matching": {"priority": 10, "patterns": ["analyze {material_id}"]},
            "inputs": {"required": ["material_id"]},
            "execution": {"mode": "sequential", "on_error": "fail_fast"},
            "steps": [{"id": "s1", "skill_id": "get_material_data"}],
        }
    )
    workflow_b = _compile(
        {
            "id": "beta_workflow",
            "name": "Beta",
            "version": "1.0.0",
            "description": "test",
            "matching": {"priority": 10, "patterns": ["analyze {material_id}"]},
            "inputs": {"required": ["material_id"]},
            "execution": {"mode": "sequential", "on_error": "fail_fast"},
            "steps": [{"id": "s1", "skill_id": "get_material_data"}],
        }
    )

    matches = match_workflows("analyze SS347", [workflow_b, workflow_a])
    assert len(matches) == 2
    assert matches[0].workflow_id == "alpha_workflow"
    assert matches[1].workflow_id == "beta_workflow"


def test_compile_detects_dependency_cycles() -> None:
    raw = {
        "id": "cycle_workflow",
        "name": "Cycle",
        "version": "1.0.0",
        "description": "test",
        "matching": {"priority": 1, "patterns": ["cycle"]},
        "execution": {"mode": "dag", "on_error": "fail_fast"},
        "steps": [
            {"id": "a", "skill_id": "s_a", "depends_on": ["b"]},
            {"id": "b", "skill_id": "s_b", "depends_on": ["a"]},
        ],
    }
    with pytest.raises(WorkflowCompileError):
        _compile(raw)


def test_compile_does_not_promote_optional_input_bindings_to_required() -> None:
    workflow = _compile(
        {
            "id": "optional_inputs",
            "name": "Optional Inputs",
            "version": "1.0.0",
            "description": "test",
            "matching": {"patterns": ["optional"]},
            "inputs": {
                "required": ["material_id"],
                "optional": ["context.temperature_c"],
            },
            "execution": {"mode": "sequential", "on_error": "fail_fast"},
            "steps": [
                {
                    "id": "analyze",
                    "skill_id": "analyze_thermal",
                    "params": {
                        "material_id": {"from": "input.material_id"},
                        "context": {
                            "temperature_c": {
                                "from": "input.context.temperature_c",
                                "optional": True,
                            },
                            "pressure_mpa": {
                                "from": "input.context.pressure_mpa",
                                "optional": True,
                            },
                        },
                    },
                }
            ],
        }
    )

    assert workflow.required_input_paths == ["material_id"]


def test_compile_infers_required_inputs_from_step_skill_requirements() -> None:
    input_schema = {
        "type": "object",
        "properties": {
            "material_id": {"type": "string"},
            "context": {
                "type": "object",
                "properties": {
                    "temperature_c": {"type": "number"},
                    "pressure_mpa": {"type": "number"},
                    "operating_hours": {"type": "integer"},
                },
                "required": ["temperature_c", "pressure_mpa", "operating_hours"],
            },
        },
        "required": ["material_id", "context"],
    }

    capabilities = {
        "analyze_thermal": _capability("analyze_thermal", input_schema=input_schema),
        "get_material_data": _capability("get_material_data"),
    }

    workflow = compile_workflow(
        raw={
            "id": "schema_required_inputs",
            "name": "Schema Required Inputs",
            "version": "1.0.0",
            "description": "test",
            "matching": {"patterns": ["schema"]},
            "inputs": {"required": ["material_id"], "optional": ["context.temperature_c"]},
            "execution": {"mode": "dag", "on_error": "fail_fast"},
            "steps": [
                {
                    "id": "retrieve",
                    "skill_id": "get_material_data",
                    "params": {"material_id": {"from": "input.material_id"}},
                    "outputs": [{"to_context": "material_data", "from": "result"}],
                },
                {
                    "id": "thermal",
                    "skill_id": "analyze_thermal",
                    "depends_on": ["retrieve"],
                    "params": {
                        "material_id": {"from": "input.material_id"},
                        "context": {
                            "temperature_c": {"from": "input.context.temperature_c", "optional": True},
                            "pressure_mpa": {"from": "input.context.pressure_mpa", "optional": True},
                            "operating_hours": {"from": "input.context.operating_hours", "optional": True},
                        },
                    },
                },
            ],
        },
        source_path=Path("test.yaml"),
        capabilities_by_skill=capabilities,
        strict=True,
    )

    assert workflow.required_input_paths == [
        "context.operating_hours",
        "context.pressure_mpa",
        "context.temperature_c",
        "material_id",
    ]


def test_registry_input_form_uses_overrides_then_agent_metadata() -> None:
    workflow_yaml = """
id: workflow_form_test
name: Workflow Form Test
version: "1.0.0"
description: test
matching:
  patterns: ["test"]
inputs:
  required:
    - context.temperature_c
    - context.pressure_mpa
execution:
  mode: sequential
  on_error: fail_fast
steps:
  - id: analyze
    skill_id: analyze_thermal
ui:
  input_overrides:
    context.temperature_c:
      label: Coolant temperature
      description: Operating coolant temperature in Celsius.
      type: number
      unit: C
"""
    input_schema = {
        "type": "object",
        "properties": {
            "context": {
                "type": "object",
                "properties": {
                    "temperature_c": {
                        "type": "number",
                        "title": "Temperature",
                        "description": "Temperature in Celsius",
                    },
                    "pressure_mpa": {
                        "type": "number",
                        "title": "System pressure",
                        "description": "Primary pressure in MPa",
                    },
                },
                "required": ["temperature_c", "pressure_mpa"],
            }
        },
        "required": ["context"],
    }
    capabilities = [_capability("analyze_thermal", input_schema=input_schema)]

    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "workflow_form_test.yaml"
        path.write_text(workflow_yaml, encoding="utf-8")

        registry = WorkflowRegistry(workflows_dir=tmp_dir, strict=True)
        refresh_result = registry.refresh(capabilities)
        assert refresh_result["count"] == 1
        assert refresh_result["errors"] == []

        form = registry.build_input_form(
            workflow_id="workflow_form_test",
            version="1.0.0",
            capabilities_by_skill={cap.skill_id: cap for cap in capabilities},
            params={},
            context={},
        )

    fields = {field["field"]: field for field in form["fields"]}
    assert fields["context.temperature_c"]["label"] == "Coolant temperature"
    assert fields["context.temperature_c"]["source"] == "workflow_override"
    assert fields["context.pressure_mpa"]["label"] == "System pressure"
    assert fields["context.pressure_mpa"]["description"] == "Primary pressure in MPa"
    assert fields["context.pressure_mpa"]["source"] == "agent_card"


def test_registry_input_form_descriptions_include_units() -> None:
    workflow_yaml = """
id: workflow_unit_desc_test
name: Workflow Unit Description Test
version: "1.0.0"
description: test
matching:
  patterns: ["unit test"]
inputs:
  required:
    - context.temperature_c
    - context.pressure_mpa
execution:
  mode: sequential
  on_error: fail_fast
steps:
  - id: analyze
    skill_id: analyze_thermal
ui:
  input_overrides:
    context.temperature_c:
      label: Coolant temperature
      description: Operating coolant temperature.
      type: number
      unit: C
"""
    input_schema = {
        "type": "object",
        "properties": {
            "context": {
                "type": "object",
                "properties": {
                    "temperature_c": {
                        "type": "number",
                        "title": "Temperature",
                        "description": "Temperature",
                    },
                    "pressure_mpa": {
                        "type": "number",
                        "title": "System pressure",
                        "description": "Primary pressure",
                        "unit": "MPa",
                    },
                },
                "required": ["temperature_c", "pressure_mpa"],
            }
        },
        "required": ["context"],
    }
    capabilities = [_capability("analyze_thermal", input_schema=input_schema)]

    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "workflow_unit_desc_test.yaml"
        path.write_text(workflow_yaml, encoding="utf-8")

        registry = WorkflowRegistry(workflows_dir=tmp_dir, strict=True)
        refresh_result = registry.refresh(capabilities)
        assert refresh_result["count"] == 1
        assert refresh_result["errors"] == []

        form = registry.build_input_form(
            workflow_id="workflow_unit_desc_test",
            version="1.0.0",
            capabilities_by_skill={cap.skill_id: cap for cap in capabilities},
            params={},
            context={},
        )

    fields = {field["field"]: field for field in form["fields"]}
    assert fields["context.temperature_c"]["description"].endswith("Unit: C.")
    assert fields["context.pressure_mpa"]["description"].endswith("Unit: MPa.")


def test_executor_error_policy_fail_fast_vs_continue_with_partial() -> None:
    async def invoke(skill_id: str, params: Dict[str, Any], conversation_id: str) -> Dict[str, Any]:
        if skill_id == "fail_skill":
            return {"error": "boom"}
        return {"result": {"ok": skill_id, "conversation_id": conversation_id, "params": params}}

    base_steps = [
        {"id": "first", "skill_id": "fail_skill"},
        {"id": "second", "skill_id": "ok_skill"},
        {"id": "third", "skill_id": "ok_skill_2", "depends_on": ["second"]},
    ]

    fail_fast_workflow = _compile(
        {
            "id": "fail_fast",
            "name": "Fail Fast",
            "version": "1.0.0",
            "description": "test",
            "matching": {"patterns": ["x"]},
            "execution": {"mode": "sequential", "on_error": "fail_fast"},
            "steps": base_steps,
        }
    )
    continue_workflow = _compile(
        {
            "id": "continue_partial",
            "name": "Continue Partial",
            "version": "1.0.0",
            "description": "test",
            "matching": {"patterns": ["x"]},
            "execution": {"mode": "sequential", "on_error": "continue_with_partial"},
            "steps": base_steps,
        }
    )

    fail_fast_result = asyncio.run(
        execute_workflow(
            workflow=fail_fast_workflow,
            input_params={},
            context={},
            invoke_skill=invoke,
            conversation_id="conv-1",
        )
    )
    continue_result = asyncio.run(
        execute_workflow(
            workflow=continue_workflow,
            input_params={},
            context={},
            invoke_skill=invoke,
            conversation_id="conv-2",
        )
    )

    assert fail_fast_result["step_statuses"]["first"] == "failed"
    assert fail_fast_result["step_statuses"]["second"] == "blocked"
    assert fail_fast_result["step_statuses"]["third"] == "blocked"

    assert continue_result["step_statuses"]["first"] == "failed"
    assert continue_result["step_statuses"]["second"] == "succeeded"
    assert continue_result["step_statuses"]["third"] == "succeeded"
