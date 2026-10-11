# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Tool-calling helpers for provider-agnostic chat completions.

Proxy chat responses arrive as plain dictionaries while LiteLLM SDK responses arrive as
objects, so every accessor here tolerates both shapes. Parsing is deliberately lenient:
``parse_tool_calls`` never raises on model-authored output, and ``require_tool_calls`` is
the single strict gate callers opt into.

This module must not import :mod:`prometheus_api.llm_client.client` at runtime so the
client can import tool parsing without a circular import.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .exceptions import LLMToolCallError
from .models import ChatResponse

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime import cycle
    from .client import AsyncLLMClient, LLMClient
    from .normalization import ChatInput


def _empty_parameters() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


@dataclass(frozen=True)
class ToolCall:
    """One normalized OpenAI-style tool call read off a chat response.

    ``arguments`` is always a decoded JSON object. When the provider sent something that
    is not a decodable JSON object, ``arguments`` is empty and ``arguments_error``
    explains why, rather than the parse raising.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    arguments_error: str | None = None
    raw: Any = None

    def __hash__(self) -> int:
        # The generated hash would hash the ``arguments`` dict and raise TypeError, so hash
        # a canonical encoding instead. ``raw`` is provider-shaped and may be unhashable.
        encoded = json.dumps(self.arguments, sort_keys=True, default=str)
        return hash((self.id, self.name, encoded, self.arguments_error))


@dataclass(frozen=True)
class ToolDefinition:
    """A developer-authored tool the model may call."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=_empty_parameters)

    def __hash__(self) -> int:
        # The generated hash would hash the ``parameters`` dict and raise TypeError.
        encoded = json.dumps(self.parameters, sort_keys=True, default=str)
        return hash((self.name, self.description, encoded))

    def as_schema(self) -> dict[str, Any]:
        """Return this definition as an OpenAI-style function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }

    @classmethod
    def from_pydantic(
        cls,
        name: str,
        model: type[BaseModel],
        *,
        description: str = "",
    ) -> ToolDefinition:
        """Build a definition whose parameters come from a Pydantic model's JSON schema."""
        return cls(name=name, description=description, parameters=_model_json_schema(model))


def _model_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    # mypy rejects a non-model at the call site; this guards untyped callers.
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise LLMToolCallError(
            f"{getattr(model, '__name__', model)!r} does not expose a JSON schema; "
            "pass a Pydantic model or build ToolDefinition.parameters directly"
        )
    return model.model_json_schema()


def _get(value: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping-shaped or attribute-shaped provider payload."""
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_dict(value: Any) -> dict[str, Any]:
    # Drop null fields on both branches so a proxy dict and a LiteLLM object for the same
    # logical message produce the same replayable shape.
    if isinstance(value, Mapping):
        return {key: item for key, item in value.items() if item is not None}
    for attribute in ("model_dump", "dict"):
        dumper = getattr(value, attribute, None)
        if callable(dumper):
            dumped = dumper(exclude_none=True)
            if isinstance(dumped, Mapping):
                return dict(dumped)
    raise LLMToolCallError(f"Expected an LLM message mapping, got {type(value).__name__}")


def _unwrap(value: Any) -> Any:
    return value.raw if isinstance(value, ChatResponse) else value


def _is_list_like(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _first_choice(value: Any) -> Any:
    choices = _get(_unwrap(value), "choices", []) or []
    if not _is_list_like(choices) or not choices:
        return None
    return choices[0]


def _decode_arguments(value: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(value, Mapping):
        return dict(value), None
    if value is None:
        return {}, None
    if not isinstance(value, str):
        return {}, (
            "tool-call arguments must be a JSON object string or a mapping, "
            f"got {type(value).__name__}"
        )
    text = value.strip()
    if not text:
        return {}, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"tool-call arguments are not valid JSON: {exc}"
    if not isinstance(parsed, dict):
        return {}, (
            f"tool-call arguments must decode to a JSON object, got {type(parsed).__name__}"
        )
    return parsed, None


def parse_tool_calls(value: ChatResponse | Any) -> tuple[ToolCall, ...]:
    """Read tool calls from a ``ChatResponse`` or a raw provider payload.

    Returns an empty tuple when the payload carries no choices, message, or tool calls.
    Never raises for provider-shaped input.
    """
    choice = _first_choice(value)
    if choice is None:
        return ()
    message = _get(choice, "message", None)
    if message is None:
        return ()

    entries = _get(message, "tool_calls", []) or []
    if not _is_list_like(entries):
        return ()

    calls: list[ToolCall] = []
    for entry in entries:
        function = _get(entry, "function", {}) or {}
        arguments, arguments_error = _decode_arguments(_get(function, "arguments", "{}"))
        calls.append(
            ToolCall(
                id=str(_get(entry, "id", "") or "").strip(),
                name=str(_get(function, "name", "") or "").strip(),
                arguments=arguments,
                arguments_error=arguments_error,
                raw=entry,
            )
        )
    return tuple(calls)


def parse_finish_reason(value: ChatResponse | Any) -> str | None:
    """Read ``choices[0].finish_reason`` from either response shape.

    This is for observability, not control flow. Do **not** terminate a multi-turn
    tool conversation on ``finish_reason == "stop"``: some providers return ``"stop"``
    alongside tool calls, so treating it as terminal silently discards them. Terminate
    on ``not response.tool_calls`` instead.
    """
    choice = _first_choice(value)
    if choice is None:
        return None
    reason = _get(choice, "finish_reason", None)
    return str(reason) if reason else None


def assistant_message(response: ChatResponse) -> dict[str, Any]:
    """Return a replayable assistant message preserving the provider's ``tool_calls``.

    A pure tool-call turn has no content. This keeps ``content`` as ``None`` rather than
    inventing placeholder text, which some providers reject on the following turn.
    """
    choice = _first_choice(response)
    message = _get(choice, "message", None) if choice is not None else None
    if message is None:
        raise LLMToolCallError("LLM response did not include a completion message")

    normalized = _as_dict(message)
    normalized["role"] = str(normalized.get("role") or "assistant")
    content = normalized.get("content")
    if content is None or (isinstance(content, str) and not content.strip()):
        normalized["content"] = None
    return normalized


EMPTY_TOOL_RESULT = "(empty result)"


def tool_result_message(call: ToolCall | str, result: Any) -> dict[str, Any]:
    """Build the ``role: "tool"`` reply that answers one tool call.

    A blank string result is replaced with :data:`EMPTY_TOOL_RESULT`, because chat
    normalization and several providers reject empty message content.
    """
    call_id = call.id if isinstance(call, ToolCall) else str(call or "").strip()
    content = result if isinstance(result, str) else json.dumps(result, default=str)
    if not content.strip():
        content = EMPTY_TOOL_RESULT
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def require_tool_calls(
    response: ChatResponse,
    *,
    expected: Sequence[str] | None = None,
    count: int | None = None,
) -> tuple[ToolCall, ...]:
    """Return the response's tool calls, raising unless they satisfy the contract.

    This is the strict counterpart to the lenient ``parse_tool_calls``.
    """
    calls = tuple(getattr(response, "tool_calls", ()) or ()) or parse_tool_calls(response)
    if not calls:
        raise LLMToolCallError("LLM response did not include any tool calls")

    allowed = {str(name) for name in expected} if expected is not None else None
    for index, call in enumerate(calls):
        if not call.id:
            raise LLMToolCallError(f"LLM tool call at index {index} is missing an id")
        if not call.name:
            raise LLMToolCallError(f"LLM tool call at index {index} is missing a function name")
        if call.arguments_error:
            raise LLMToolCallError(
                f"LLM tool call {call.name!r} has invalid arguments: {call.arguments_error}"
            )
        if allowed is not None and call.name not in allowed:
            available = ", ".join(sorted(allowed)) or "none"
            raise LLMToolCallError(
                f"LLM tool call {call.name!r} is not an expected tool. Expected: {available}."
            )

    if count is not None and len(calls) != count:
        raise LLMToolCallError(
            f"LLM returned {len(calls)} tool calls but exactly {count} were required"
        )
    return calls


def tool_schemas(
    definitions: Iterable[ToolDefinition | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert tool definitions to OpenAI function schemas, passing mappings through."""
    schemas: list[dict[str, Any]] = []
    for definition in definitions:
        if isinstance(definition, ToolDefinition):
            schemas.append(definition.as_schema())
        elif isinstance(definition, Mapping):
            schemas.append(dict(definition))
        else:
            raise LLMToolCallError(
                "Tools must be ToolDefinition values or OpenAI function schema mappings, "
                f"got {type(definition).__name__}"
            )
    return schemas


def _forced_tool_name(tool: ToolDefinition | Mapping[str, Any]) -> str:
    if isinstance(tool, ToolDefinition):
        name = tool.name
    else:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        name = str(_get(function or {}, "name", "") or "")
    name = name.strip()
    if not name:
        raise LLMToolCallError("A forced tool call requires a non-empty tool name")
    return name


def _forced_tool_choice(name: str) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name}}


def call_tool(
    client: LLMClient,
    text_or_messages: ChatInput,
    *,
    tool: ToolDefinition | Mapping[str, Any],
    model: str | None = None,
    **kwargs: Any,
) -> ToolCall:
    """Force one named tool call and return it, raising unless exactly one came back."""
    name = _forced_tool_name(tool)
    response = client.chat(
        text_or_messages,
        model=model,
        tools=[tool],
        tool_choice=_forced_tool_choice(name),
        **kwargs,
    )
    return require_tool_calls(response, expected=[name], count=1)[0]


async def acall_tool(
    client: AsyncLLMClient,
    text_or_messages: ChatInput,
    *,
    tool: ToolDefinition | Mapping[str, Any],
    model: str | None = None,
    **kwargs: Any,
) -> ToolCall:
    """Async counterpart to :func:`call_tool`."""
    name = _forced_tool_name(tool)
    response = await client.chat(
        text_or_messages,
        model=model,
        tools=[tool],
        tool_choice=_forced_tool_choice(name),
        **kwargs,
    )
    return require_tool_calls(response, expected=[name], count=1)[0]
