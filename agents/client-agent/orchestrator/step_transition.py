"""LLM-mediated parameter mapping at sequential chain step boundaries.

In a sequential plan, the inputs of a downstream step refer to the chain's
own dataflow: artifacts produced by earlier steps, but also values an
earlier step only stated in its result text (a recommended element size, a
computed temperature). At plan time those values do not exist, so binding
is deferred to runtime — and at runtime there is no user message to extract
from, only step outputs.

This module makes the step boundary work like a turn boundary: an LLM reads
the completed steps' result text and artifact metadata plus the next step's
input schema, and returns parameter updates. Guardrails keep it honest:

- artifact-reference params may only be set to ids that actually exist
  (chain-produced or conversation catalog); anything else is dropped;
- non-artifact params are fill-only — a value the planner extracted from
  the user is never overridden by chain output;
- on LLM failure or unusable output, binding falls back to the
  deterministic metadata matcher (``bind_produced_artifacts``).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from artifact_handling import bind_produced_artifacts, extract_artifact_field_paths
from param_schema import flatten_schema_properties, get_nested_value, set_nested_value

from . import runtime

MAX_STEP_TEXT_CHARS = 2000
MAX_CATALOG_ARTIFACTS = 12
MAX_ARTIFACT_DESC_CHARS = 200


def _parse_param_updates(text: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM response as a JSON object (possibly fenced/prefixed).

    Not ``utils.extract_json_from_text`` — that helper matches raw JSON
    arrays before objects, so an object containing an array value would be
    parsed as the inner array.
    """
    candidates = [text]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _format_artifact_line(artifact: Dict[str, Any]) -> str:
    mime = str(artifact.get("mime_type") or "unknown mime")
    description = str(artifact.get("description") or "").strip()[:MAX_ARTIFACT_DESC_CHARS]
    line = (
        f"- artifact_id: {artifact.get('artifact_id')}"
        f" | name: {artifact.get('name')}"
        f" | mime: {mime}"
    )
    return f"{line} | {description}" if description else line


def _coerce_param_value(value: Any, prop: Dict[str, Any]) -> Optional[Any]:
    """Coerce an LLM-supplied value to the schema property's type.

    Returns None to signal "drop this update" — when the value violates an
    enum or cannot be converted to a declared numeric/boolean type, the param
    is left unchanged rather than set to a malformed value. Unknown or missing
    ``type`` falls through to a passthrough of the original value.
    """
    enum = prop.get("enum")
    if isinstance(enum, list) and enum and value not in enum:
        return None
    prop_type = str(prop.get("type") or "").lower()
    try:
        if prop_type == "number":
            return float(value)
        if prop_type == "integer":
            return int(value)
    except (TypeError, ValueError):
        return None
    if prop_type == "boolean":
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
        return None
    if prop_type == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        return None
    if prop_type == "array":
        return value if isinstance(value, list) else None
    if prop_type == "object":
        return value if isinstance(value, dict) else None
    return value


def _build_transition_prompt(
    *,
    skill_id: str,
    capability_description: str,
    properties: Dict[str, Any],
    artifact_paths: Dict[str, str],
    params: Dict[str, Any],
    chain_steps: List[Dict[str, Any]],
    catalog: List[Dict[str, Any]],
    user_query: str,
) -> str:
    step_blocks: List[str] = []
    chain_artifact_ids: set = set()
    for index, step in enumerate(chain_steps, start=1):
        lines = [f"Step {index} — skill: {step.get('skill_id')}"]
        text = str(step.get("result_text") or "").strip()
        if len(text) > MAX_STEP_TEXT_CHARS:
            text = text[:MAX_STEP_TEXT_CHARS] + " …[truncated]"
        if text:
            lines.append("Output text:")
            lines.append(text)
        artifacts = [a for a in (step.get("artifacts") or []) if isinstance(a, dict)]
        if artifacts:
            lines.append("Artifacts produced:")
            for artifact in artifacts:
                lines.append(_format_artifact_line(artifact))
                chain_artifact_ids.add(str(artifact.get("artifact_id") or ""))
        step_blocks.append("\n".join(lines))

    catalog_rows = [
        _format_artifact_line(artifact)
        for artifact in catalog[:MAX_CATALOG_ARTIFACTS]
        if str(artifact.get("artifact_id") or "") not in chain_artifact_ids
    ]
    catalog_block = (
        "PRE-EXISTING CONVERSATION ARTIFACTS (only relevant when the user request explicitly refers to them):\n"
        + "\n".join(catalog_rows)
        if catalog_rows
        else ""
    )

    param_lines: List[str] = []
    for path, prop in sorted(properties.items()):
        if not isinstance(prop, dict):
            continue
        is_object = prop.get("type") == "object" or "properties" in prop
        if is_object and path not in artifact_paths:
            continue
        marker = (
            f" [ARTIFACT REFERENCE — {artifact_paths[path]}]" if path in artifact_paths else ""
        )
        description = str(prop.get("description") or "").strip() or "no description"
        current = get_nested_value(params, path)
        param_lines.append(
            f"- {path} (type: {prop.get('type', 'string')}){marker}: {description}"
            f" | current value: {json.dumps(current, default=str)}"
        )

    sections = [
        "You map the outputs of completed workflow steps onto the input parameters "
        "of the next step in a multi-step plan.",
        f"ORIGINAL USER REQUEST:\n{user_query}",
        "COMPLETED STEPS (execution order):\n" + "\n\n".join(step_blocks),
    ]
    if catalog_block:
        sections.append(catalog_block)
    sections.append(
        f"NEXT STEP: {skill_id} — {capability_description}\n"
        "INPUT PARAMETERS:\n" + "\n".join(param_lines)
    )
    sections.append(
        "Respond with ONLY a JSON object mapping dotted parameter paths to values.\n"
        "Rules:\n"
        "- Parameters marked [ARTIFACT REFERENCE] must be set to an artifact_id "
        "listed above. Prefer artifacts produced by the completed steps; re-bind any "
        "artifact reference whose current value is not one of those ids, unless the "
        "user request explicitly refers to a pre-existing artifact. The 'multiple' "
        "mode takes a JSON array of artifact ids.\n"
        "- For other parameters, only supply values explicitly grounded in the "
        "completed steps' outputs or the user request (e.g. a quantity the previous "
        "step computed or recommended). Never guess or invent values.\n"
        "- Do not include parameters whose current value should stay unchanged.\n"
        "- Return {} if nothing should change."
    )
    return "\n\n".join(sections)


async def resolve_step_transition_params(
    *,
    skill_id: str,
    capability: Any,
    params: Dict[str, Any],
    chain_steps: List[Dict[str, Any]],
    produced_artifacts: List[Dict[str, Any]],
    user_query: str,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Map completed-step outputs onto the next step's input parameters."""
    input_schema = getattr(capability, "input_schema", None)
    if not isinstance(input_schema, dict):
        input_schema = None
    if not chain_steps or not input_schema:
        return bind_produced_artifacts(params, input_schema, produced_artifacts)

    properties = flatten_schema_properties(input_schema)
    artifact_paths = extract_artifact_field_paths(input_schema)
    if not properties:
        return bind_produced_artifacts(params, input_schema, produced_artifacts)

    catalog = [a for a in (params.get("artifacts") or []) if isinstance(a, dict)]
    valid_ids = {str(a.get("artifact_id") or "") for a in produced_artifacts}
    valid_ids |= {str(a.get("artifact_id") or "") for a in catalog}
    valid_ids.discard("")

    prompt = _build_transition_prompt(
        skill_id=skill_id,
        capability_description=str(getattr(capability, "description", "") or ""),
        properties=properties,
        artifact_paths=artifact_paths,
        params=params,
        chain_steps=chain_steps,
        catalog=catalog,
        user_query=user_query,
    )

    parsed: Any = None
    try:
        runtime.store_status_update(
            conversation_id,
            f"Mapping completed-step outputs onto '{skill_id}' inputs.",
        )
        async with runtime.create_llm() as llm:
            response = await llm.medium(prompt, temperature=0, max_tokens=4096)
        parsed = _parse_param_updates(response.text)
    except Exception as exc:
        print(f"[WARN] Step-transition LLM mapping failed for '{skill_id}': {exc}")

    if not isinstance(parsed, dict):
        return bind_produced_artifacts(params, input_schema, produced_artifacts)

    resolved = dict(params)
    artifact_choices: Dict[str, Any] = {}
    for path, value in parsed.items():
        if path not in properties:
            continue
        if path in artifact_paths:
            if artifact_paths[path] == "multiple":
                if not isinstance(value, list):
                    continue
                ids = [str(item) for item in value if str(item) in valid_ids]
                if ids:
                    artifact_choices[path] = ids
            else:
                if not isinstance(value, (str, int)) or str(value) not in valid_ids:
                    continue
                artifact_choices[path] = str(value)
        else:
            if value is None or get_nested_value(resolved, path) is not None:
                continue
            coerced = _coerce_param_value(value, properties.get(path) or {})
            if coerced is not None:
                set_nested_value(resolved, path, coerced)

    # Deterministic baseline for artifact params the LLM left untouched, then
    # the LLM's explicit, validated choices win (it may deliberately bind a
    # catalog artifact the matcher would override).
    resolved = bind_produced_artifacts(resolved, input_schema, produced_artifacts)
    for path, value in artifact_choices.items():
        set_nested_value(resolved, path, value)
    return resolved
