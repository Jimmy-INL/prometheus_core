"""Tests for the schema-bound parameter extraction stage."""

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

from orchestrator import parameter_extraction  # noqa: E402


BUTTERFLY_VALVE_SCHEMA = {
    "type": "object",
    "properties": {
        "input_data": {
            "type": "object",
            "description": "Structured butterfly-valve dimensions. Length values are in metres.",
            "properties": {
                "equipment_type": {
                    "type": "string",
                    "enum": ["butterfly_valve"],
                },
                "pipe_diameter": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "Pipe diameter in metres.",
                },
                "num_holes": {
                    "type": "integer",
                    "minimum": 1,
                },
                "hole_diameter": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "Bolt-hole diameter in metres.",
                },
                "rod_diameter": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "Actuator rod diameter in metres.",
                },
                "runtime_mesh": {
                    "type": "object",
                    "x_input_source": "runtime",
                },
            },
            "required": [
                "equipment_type",
                "pipe_diameter",
                "num_holes",
                "hole_diameter",
                "rod_diameter",
                "runtime_mesh",
            ],
        },
    },
    "required": ["input_data"],
}


def _capability(skill_id: str = "author_equipment_geometry"):
    return SimpleNamespace(
        skill_id=skill_id,
        skill_name="Author Equipment Geometry",
        description="Create parameterized equipment geometry.",
        input_schema=BUTTERFLY_VALVE_SCHEMA,
    )


def _tool_response(tool_name: str, arguments: dict):
    return SimpleNamespace(
        raw={
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "extract-1",
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def medium(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


def test_partial_extraction_schema_preserves_contract_and_excludes_runtime_fields():
    schema = parameter_extraction.build_partial_extraction_schema(
        BUTTERFLY_VALVE_SCHEMA
    )

    assert "required" not in schema
    assert schema["additionalProperties"] is False
    input_data = schema["properties"]["input_data"]
    assert "required" not in input_data
    assert input_data["additionalProperties"] is False
    assert "runtime_mesh" not in input_data["properties"]
    assert input_data["properties"]["equipment_type"]["enum"] == [
        "butterfly_valve"
    ]
    assert input_data["properties"]["pipe_diameter"]["exclusiveMinimum"] == 0
    assert (
        input_data["properties"]["hole_diameter"]["description"]
        == "Bolt-hole diameter in metres."
    )


def test_extract_parameters_uses_exact_nested_tool_schema(monkeypatch):
    tool_name = parameter_extraction.extraction_tool_name(
        1, "author_equipment_geometry"
    )
    fake_llm = _FakeLLM(
        _tool_response(
            tool_name,
            {
                "input_data": {
                    "equipment_type": "butterfly_valve",
                    "pipe_diameter": 0.9,
                    "num_holes": 6,
                    "hole_diameter": 0.05,
                }
            },
        )
    )
    monkeypatch.setattr(
        parameter_extraction.runtime,
        "create_llm",
        lambda: fake_llm,
    )

    result = asyncio.run(
        parameter_extraction.extract_parameters_with_schemas(
            query=(
                "Create a butterfly valve for a pipe diameter of 0.9m and "
                "6 holes with a 5cm diameter each."
            ),
            capabilities=[_capability()],
            history=[],
            context={},
        )
    )

    assert result == {
        "input_data": {
            "equipment_type": "butterfly_valve",
            "pipe_diameter": 0.9,
            "num_holes": 6,
            "hole_diameter": 0.05,
        }
    }
    _, kwargs = fake_llm.calls[0]
    assert kwargs["temperature"] == 0
    assert len(kwargs["tools"]) == 1
    function = kwargs["tools"][0]["function"]
    assert function["name"] == tool_name
    assert function["parameters"]["properties"] == (
        parameter_extraction.build_partial_extraction_schema(
            BUTTERFLY_VALVE_SCHEMA
        )["properties"]
    )


def test_extract_parameters_rejects_aliases_and_wrong_nesting(monkeypatch):
    tool_name = parameter_extraction.extraction_tool_name(
        1, "author_equipment_geometry"
    )
    fake_llm = _FakeLLM(
        _tool_response(
            tool_name,
            {
                "equipment_type": "butterfly_valve",
                "pipe_diameter_m": 0.9,
                "hole_count": 6,
                "hole_diameter_m": 0.05,
            },
        )
    )
    monkeypatch.setattr(
        parameter_extraction.runtime,
        "create_llm",
        lambda: fake_llm,
    )

    with pytest.raises(
        parameter_extraction.ParameterExtractionError,
        match="author_equipment_geometry.*schema",
    ):
        asyncio.run(
            parameter_extraction.extract_parameters_with_schemas(
                query="Create a butterfly valve.",
                capabilities=[_capability()],
                history=[],
                context={},
            )
        )


def test_extract_parameters_rejects_missing_tool_call(monkeypatch):
    fake_llm = _FakeLLM(
        SimpleNamespace(
            raw={
                "choices": [
                    {
                        "message": {
                            "content": "{}",
                            "tool_calls": [],
                        }
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        parameter_extraction.runtime,
        "create_llm",
        lambda: fake_llm,
    )

    with pytest.raises(
        parameter_extraction.ParameterExtractionError,
        match="did not call",
    ):
        asyncio.run(
            parameter_extraction.extract_parameters_with_schemas(
                query="Create a butterfly valve.",
                capabilities=[_capability()],
                history=[],
                context={},
            )
        )


def test_invocation_resolution_replaces_planning_candidates(monkeypatch):
    tool_name = parameter_extraction.extraction_tool_name(
        1, "author_equipment_geometry"
    )
    fake_llm = _FakeLLM(
        _tool_response(
            tool_name,
            {"input_data": {"hole_diameter": 0.10}},
        )
    )
    monkeypatch.setattr(
        parameter_extraction.runtime,
        "create_llm",
        lambda: fake_llm,
    )

    result = asyncio.run(
        parameter_extraction.extract_parameters_with_schemas(
            query="Double the hole diameter.",
            capabilities=[_capability()],
            history=[],
            context={},
            existing_params={
                "input_data": {
                    "equipment_type": "butterfly_valve",
                    "hole_diameter": 0.05,
                }
            },
            replace_existing=True,
        )
    )

    assert result["input_data"] == {
        "equipment_type": "butterfly_valve",
        "hole_diameter": 0.10,
    }
    system_prompt = fake_llm.calls[0][0][0]["content"]
    assert "current instruction is authoritative" in system_prompt
    assert "_operation_dependencies" in system_prompt
