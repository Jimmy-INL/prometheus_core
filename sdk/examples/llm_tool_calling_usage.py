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

"""LLM tool-calling usage examples.

Tool calling is a per-call capability of any chat alias, so it needs no extra
configuration beyond a working LLMClient setup.

Run with the default LiteLLM registry profile:

    REGISTRY_URL=http://localhost:4000 uv run python examples/llm_tool_calling_usage.py

Or an installed direct-provider profile:

    LLM_CONFIG_PROFILE=openai OPENAI_API_KEY=... uv run python examples/llm_tool_calling_usage.py
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from prometheus_api.llm_client import (
    LLMAliasError,
    LLMClient,
    LLMConfig,
    LLMToolCallError,
    ToolCall,
    ToolDefinition,
    assistant_message,
    call_tool,
    require_tool_calls,
    tool_result_message,
)

# --------------------------------------------------------------------------- tools


class LookupMaterial(BaseModel):
    """Look up a material's physical properties by name."""

    name: str = Field(description="Material name, for example 'iron' or 'stainless steel 316'")


class ConvertUnits(BaseModel):
    """Convert a value between two units."""

    value: float = Field(description="The numeric value to convert")
    from_unit: str = Field(description="Source unit, for example 'g/cm3'")
    to_unit: str = Field(description="Target unit, for example 'kg/m3'")


TOOLS = [
    ToolDefinition.from_pydantic(
        "lookup_material",
        LookupMaterial,
        description="Look up a material's physical properties by name.",
    ),
    ToolDefinition.from_pydantic(
        "convert_units",
        ConvertUnits,
        description="Convert a value between two units.",
    ),
]

_MATERIALS = {
    "iron": {"density": 7.87, "unit": "g/cm3", "melting_point_c": 1538},
    "aluminum": {"density": 2.70, "unit": "g/cm3", "melting_point_c": 660},
}


def lookup_material(arguments: dict) -> dict:
    """Stand-in for a real material database call."""
    name = str(arguments.get("name", "")).strip().lower()
    return _MATERIALS.get(name, {"error": f"No record for {name!r}"})


def convert_units(arguments: dict) -> dict:
    """Stand-in for a real unit-conversion service."""
    factors = {("g/cm3", "kg/m3"): 1000.0, ("kg/m3", "g/cm3"): 0.001}
    factor = factors.get((arguments.get("from_unit"), arguments.get("to_unit")))
    if factor is None:
        return {"error": "Unsupported conversion"}
    return {"value": float(arguments["value"]) * factor, "unit": arguments["to_unit"]}


DISPATCH = {"lookup_material": lookup_material, "convert_units": convert_units}

# Always bound a tool conversation. Each turn is a billed request with growing
# context, so an unbounded loop has no cost ceiling.
MAX_TOOL_TURNS = 8


def run_tool(call: ToolCall) -> dict | str:
    """Execute one tool call, reporting problems back to the model as text."""
    if call.arguments_error:
        return f"ERROR: {call.arguments_error}"
    function = DISPATCH.get(call.name)
    if function is None:
        return f"ERROR: unknown tool {call.name!r}"
    try:
        return function(call.arguments)
    except Exception as exc:  # noqa: BLE001 - report failures to the model, do not crash
        return f"ERROR: {type(exc).__name__}: {exc}"


# ------------------------------------------------------------------------ examples


def example_inspect_tool_calls(llm: LLMClient) -> None:
    """Show that a pure tool-call turn has no text, only tool calls."""
    print("=== Reading tool calls off a response ===")
    response = llm.medium(
        "What is the density of iron?",
        tools=TOOLS,
        tool_choice="auto",
    )

    print(f"  text:          {response.text!r}   <- empty for a pure tool-call turn")
    print(f"  finish_reason: {response.finish_reason}")
    for call in response.tool_calls:
        print(f"  tool call:     {call.name}({json.dumps(call.arguments)})  id={call.id}")
        if call.arguments_error:
            print(f"    arguments_error: {call.arguments_error}")
    if not response.tool_calls:
        print("  The model answered directly instead of calling a tool.")


def example_answer_tool_calls(llm: LLMClient) -> None:
    """Replay a tool-call turn with results so the model can finish its answer."""
    print("\n=== Replaying tool results into history ===")
    history: list[dict] = [
        {"role": "system", "content": "Use the provided tools for material facts."},
        {"role": "user", "content": "How dense is iron in kg/m3?"},
    ]

    response = llm.medium(history, tools=TOOLS, tool_choice="auto")
    if not response.tool_calls:
        print(f"  Answered without tools: {response.text}")
        return

    # assistant_message keeps content as None rather than inventing placeholder text.
    history.append(assistant_message(response))
    for call in response.tool_calls:
        result = run_tool(call)
        print(f"  {call.name}({json.dumps(call.arguments)}) -> {result}")
        history.append(tool_result_message(call, result))

    final = llm.medium(history, tools=TOOLS)
    if final.tool_calls:
        print(f"  model requested more tools: {[call.name for call in final.tool_calls]}")
    else:
        print(f"  final answer: {final.text}")


def example_bounded_tool_loop(llm: LLMClient) -> None:
    """Drive a full multi-turn tool conversation with an explicit turn budget.

    Two things here are easy to get wrong and both matter:

    1. **Terminate on the absence of tool calls**, never on ``finish_reason``. Some
       providers return ``finish_reason == "stop"`` alongside tool calls; treating
       that as terminal silently discards the tools the model asked for.
    2. **Bound the turns.** An unbounded ``while True`` against a metered provider
       keeps paying for turns as long as the model keeps requesting tools.
    """
    print("\n=== Bounded multi-turn tool loop ===")
    history: list[dict] = [
        {"role": "system", "content": "Use the provided tools for material facts."},
        {
            "role": "user",
            "content": "How dense is iron, in kg/m3? Look it up, then convert the units.",
        },
    ]

    for turn in range(1, MAX_TOOL_TURNS + 1):
        response = llm.medium(history, tools=TOOLS, tool_choice="auto")

        # The terminator is the absence of tool calls. Do not check finish_reason.
        if not response.tool_calls:
            print(f"  turn {turn}: final answer -> {response.text}")
            return

        history.append(assistant_message(response))
        for call in response.tool_calls:
            result = run_tool(call)
            print(f"  turn {turn}: {call.name}({json.dumps(call.arguments)}) -> {result}")
            history.append(tool_result_message(call, result))

    # Exhausting the budget is a real outcome; surface it rather than returning
    # partial history that looks like a finished answer.
    print(f"  stopped after {MAX_TOOL_TURNS} turns with no final answer")


def example_strict_gate(llm: LLMClient) -> None:
    """Show the difference between lenient parsing and the strict gate."""
    print("\n=== Lenient parsing vs. the strict gate ===")
    response = llm.medium("What is the density of aluminum?", tools=TOOLS, tool_choice="auto")

    # Parsing never raises: malformed arguments arrive as data on the ToolCall.
    print(f"  parsed {len(response.tool_calls)} tool call(s) without raising")

    try:
        calls = require_tool_calls(response, expected=[tool.name for tool in TOOLS])
        print(f"  strict gate passed: {[call.name for call in calls]}")
    except LLMToolCallError as exc:
        print(f"  strict gate rejected the response: {exc}")


def example_forced_single_tool(llm: LLMClient) -> None:
    """Use a forced tool call as structured output, then validate it with Pydantic."""
    print("\n=== Forced single tool call as structured output ===")
    try:
        call = call_tool(
            llm,
            "Extract the material the user is asking about: 'tell me about aluminum'",
            tool=TOOLS[0],
            model="medium",
        )
    except LLMToolCallError as exc:
        print(f"  extraction failed: {exc}")
        return

    arguments = LookupMaterial.model_validate(call.arguments)
    print(f"  extracted: {arguments.name}")
    print(f"  properties: {lookup_material(call.arguments)}")


def print_setup_help() -> None:
    """Print local configuration guidance."""
    print("\nLocal setup:")
    print("  1. Use the default registry profile:")
    print("     export REGISTRY_URL=http://localhost:4000")
    print("  2. Or select an installed provider profile:")
    print("     export LLM_CONFIG_PROFILE=openai")
    print("  3. Export provider keys referenced by the selected YAML:")
    print("     export OPENAI_API_KEY=...")
    print("\nTool calling needs no additional environment variables.")


def main() -> None:
    """Run all tool-calling examples."""
    print("=" * 60)
    print("LLM Tool Calling Examples")
    print("=" * 60)

    config = LLMConfig.from_env()
    print(f"Proxy URL: {config.proxy_url or '(direct provider)'}")
    print(f"LLM config: {config.config_file}")
    print(f"Tools: {', '.join(tool.name for tool in TOOLS)}\n")

    try:
        with LLMClient(config) as llm:
            example_inspect_tool_calls(llm)
            example_answer_tool_calls(llm)
            example_bounded_tool_loop(llm)
            example_strict_gate(llm)
            example_forced_single_tool(llm)
    except LLMAliasError as exc:
        print(f"\nAlias configuration error:\n{exc}")
        print_setup_help()
    except Exception as exc:
        print(f"\nLLM call failed: {exc}")
        print_setup_help()


if __name__ == "__main__":
    main()
