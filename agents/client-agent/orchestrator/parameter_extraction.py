"""Schema-bound extraction of user-supplied parameters after routing."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from capability_cache import AgentCapability
from param_schema import is_user_input_schema

from . import runtime


class ParameterExtractionError(RuntimeError):
    """Raised when an extraction response violates the selected skill contract."""


def extraction_tool_name(index: int, skill_id: str) -> str:
    """Return a deterministic provider-compatible tool name."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(skill_id)).strip("_")
    return f"extract_{index}_{slug}"[:64]


def build_partial_extraction_schema(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Copy an input schema for partial extraction without weakening its shape."""

    def transform(node: Any) -> Any:
        if isinstance(node, list):
            return [transform(item) for item in node]
        if not isinstance(node, dict):
            return copy.deepcopy(node)

        transformed: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "required":
                continue
            if key == "properties" and isinstance(value, dict):
                transformed[key] = {
                    name: transform(prop)
                    for name, prop in value.items()
                    if isinstance(prop, dict) and is_user_input_schema(prop)
                }
                continue
            if key in {"$defs", "definitions", "patternProperties"} and isinstance(value, dict):
                transformed[key] = {
                    name: transform(schema)
                    for name, schema in value.items()
                }
                continue
            if key in {
                "additionalProperties",
                "contains",
                "else",
                "if",
                "items",
                "not",
                "propertyNames",
                "then",
                "unevaluatedItems",
                "unevaluatedProperties",
            }:
                transformed[key] = transform(value)
                continue
            if key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                transformed[key] = transform(value)
                continue
            transformed[key] = copy.deepcopy(value)

        is_object = transformed.get("type") == "object" or "properties" in transformed
        if (
            is_object
            and "properties" in transformed
            and "additionalProperties" not in transformed
        ):
            transformed["additionalProperties"] = False

        return transformed

    if not isinstance(input_schema, dict):
        raise ParameterExtractionError("Capability input schema must be an object.")
    partial = transform(input_schema)
    if partial.get("type") != "object" and "properties" not in partial:
        raise ParameterExtractionError(
            "Capability input schema must describe an object."
        )
    return partial


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _parse_tool_calls(raw: Any) -> List[Dict[str, Any]]:
    choices = _value(raw, "choices", []) or []
    if not choices:
        raise ParameterExtractionError(
            "Parameter extraction response has no completion choice."
        )
    message = _value(choices[0], "message", {}) or {}
    raw_calls = _value(message, "tool_calls", []) or []
    calls: List[Dict[str, Any]] = []
    for call in raw_calls:
        function = _value(call, "function", {}) or {}
        name = str(_value(function, "name", "") or "")
        arguments = _value(function, "arguments", None)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ParameterExtractionError(
                    f"Parameter extraction tool '{name}' returned malformed JSON: {exc}"
                ) from exc
        elif isinstance(arguments, Mapping):
            arguments = dict(arguments)
        if not isinstance(arguments, dict):
            raise ParameterExtractionError(
                f"Parameter extraction tool '{name}' arguments must be an object."
            )
        calls.append({"name": name, "args": arguments})
    return calls


def _validate_arguments(
    *,
    skill_id: str,
    schema: Dict[str, Any],
    arguments: Dict[str, Any],
) -> None:
    validator_class = validator_for(schema)
    try:
        validator_class.check_schema(schema)
    except Exception as exc:
        raise ParameterExtractionError(
            f"Input schema for '{skill_id}' is invalid: {exc}"
        ) from exc
    validator = validator_class(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(arguments),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    raise ParameterExtractionError(
        f"Parameter extraction for '{skill_id}' violates its input schema "
        f"at '{location}': {error.message}"
    )


def _merge_exact(
    target: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    source: str,
    prefix: str = "",
) -> None:
    for key, value in incoming.items():
        path = f"{prefix}.{key}" if prefix else key
        if key not in target:
            target[key] = copy.deepcopy(value)
            continue
        current = target[key]
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_exact(current, value, source=source, prefix=path)
            continue
        if current != value:
            raise ParameterExtractionError(
                f"Parameter extraction for '{source}' conflicts at '{path}'."
            )


def _prompt(
    *,
    query: str,
    history: List[Dict[str, Any]],
    context: Dict[str, Any],
    existing_params: Dict[str, Any],
    tool_names: List[str],
) -> List[Dict[str, str]]:
    system = (
        "You extract parameters for capabilities that have already been selected. "
        "Do not select or change capabilities. Call every extraction tool exactly "
        "once, using only values supported by the user query, conversation history, "
        "current context, or existing parameters. Preserve each tool schema's exact "
        "field names and nesting. Omit values that are not available; do not guess. "
        "Convert units only when the schema description specifies the destination "
        "unit. Return no prose."
    )
    user = (
        f"User query:\n{query}\n\n"
        f"Conversation history:\n{json.dumps(history, default=str)}\n\n"
        f"Current context:\n{json.dumps(context, default=str)}\n\n"
        f"Existing parameters:\n{json.dumps(existing_params, default=str)}\n\n"
        f"Required extraction tools:\n{json.dumps(tool_names)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def extract_parameters_with_schemas(
    *,
    query: str,
    capabilities: List[AgentCapability],
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    existing_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract partial parameters using one exact tool schema per selected skill."""
    schemas_by_tool: Dict[str, tuple[str, Dict[str, Any]]] = {}
    tools: List[Dict[str, Any]] = []
    for index, capability in enumerate(capabilities, 1):
        input_schema = getattr(capability, "input_schema", None)
        if not isinstance(input_schema, dict) or not input_schema:
            continue
        partial_schema = build_partial_extraction_schema(input_schema)
        if not partial_schema.get("properties"):
            continue
        tool_name = extraction_tool_name(index, capability.skill_id)
        schemas_by_tool[tool_name] = (capability.skill_id, partial_schema)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": (
                        f"Extract parameters for '{capability.skill_id}' using "
                        "the exact selected capability input schema."
                    ),
                    "parameters": partial_schema,
                },
            }
        )

    merged = copy.deepcopy(existing_params or {})
    if not tools:
        return merged

    tool_names = list(schemas_by_tool)
    messages = _prompt(
        query=query,
        history=list(history or []),
        context=dict(context or {}),
        existing_params=merged,
        tool_names=tool_names,
    )
    async with runtime.create_llm() as llm:
        response = await llm.medium(
            messages,
            temperature=0,
            max_tokens=2048,
            tools=tools,
        )

    calls = _parse_tool_calls(response.raw)
    received: set[str] = set()
    for call in calls:
        tool_name = call["name"]
        if tool_name not in schemas_by_tool:
            raise ParameterExtractionError(
                f"Parameter extraction returned unknown tool '{tool_name}'."
            )
        if tool_name in received:
            raise ParameterExtractionError(
                f"Parameter extraction called '{tool_name}' more than once."
            )
        received.add(tool_name)
        skill_id, schema = schemas_by_tool[tool_name]
        arguments = call["args"]
        _validate_arguments(
            skill_id=skill_id,
            schema=schema,
            arguments=arguments,
        )
        _merge_exact(merged, arguments, source=skill_id)

    missing_calls = [name for name in tool_names if name not in received]
    if missing_calls:
        raise ParameterExtractionError(
            "Parameter extraction did not call required tool(s): "
            + ", ".join(missing_calls)
        )
    return merged
