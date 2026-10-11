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

"""Workflow compiler and validator."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from .schema import CompiledPattern, CompiledWorkflow, WorkflowDefinition

if TYPE_CHECKING:
    from capability_cache import AgentCapability
else:
    AgentCapability = Any


class WorkflowCompileError(ValueError):
    """Raised when workflow validation fails in strict mode."""


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


def _compile_pattern(pattern: str) -> CompiledPattern:
    """Compile `{field}` placeholders into deterministic regex with named groups."""
    placeholder_names = _PLACEHOLDER_RE.findall(pattern)
    regex_pattern = ""
    idx = 0
    for match in _PLACEHOLDER_RE.finditer(pattern):
        start, end = match.span()
        regex_pattern += re.escape(pattern[idx:start])
        name = match.group(1).replace(".", "_")
        regex_pattern += rf"(?P<{name}>[^\s,;]+)"
        idx = end
    regex_pattern += re.escape(pattern[idx:])
    compiled = re.compile(regex_pattern, flags=re.IGNORECASE)
    specificity = len([ch for ch in pattern if ch not in "{}"]) + len(placeholder_names) * 5
    return CompiledPattern(
        source=pattern,
        regex=compiled,
        placeholder_names=placeholder_names,
        specificity=specificity,
    )


def _extract_input_binding_refs(
    value: Any,
    refs: List[Tuple[str, bool]],
    inherited_optional: bool = False,
) -> None:
    """Collect `input.*` binding refs with effective optionality.

    Optionality is inherited through nested binding nodes so parent-level
    optional sections do not accidentally become required workflow inputs.
    """
    if isinstance(value, dict):
        optional = inherited_optional or bool(value.get("optional", False))
        if "from" in value and isinstance(value.get("from"), str):
            source = str(value["from"])
            if source.startswith("input."):
                refs.append((source[len("input.") :], optional))
            return
        for v in value.values():
            _extract_input_binding_refs(v, refs, inherited_optional=optional)
    elif isinstance(value, list):
        for item in value:
            _extract_input_binding_refs(item, refs, inherited_optional=inherited_optional)


def _extract_required_schema_paths(schema: Dict[str, Any], prefix: str = "") -> List[str]:
    """Extract required leaf paths from a JSON-object schema."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return []
    properties = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []
    paths: List[str] = []
    for field in required:
        field_path = f"{prefix}{field}"
        field_schema = properties.get(field, {})
        is_object = isinstance(field_schema, dict) and (
            field_schema.get("type") == "object" or "properties" in field_schema
        )
        if is_object:
            nested = _extract_required_schema_paths(field_schema, prefix=f"{field_path}.")
            if nested:
                paths.extend(nested)
            else:
                paths.append(field_path)
        else:
            paths.append(field_path)
    return paths


def _get_binding_node(params: Dict[str, Any], path: str) -> Any:
    current: Any = params
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _resolve_required_binding_source(params: Dict[str, Any], required_path: str) -> Optional[str]:
    """Resolve where a required step input comes from.

    Returns normalized source markers:
    - `input.<path>`
    - `context.<path>`
    - `step.<...>` (runtime-produced)
    - `literal`
    - `None` when no binding is declared
    """
    node = _get_binding_node(params, required_path)
    if isinstance(node, dict) and isinstance(node.get("from"), str):
        return str(node["from"])
    if isinstance(node, dict) and "literal" in node:
        return "literal"

    parts = required_path.split(".")
    for idx in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:idx])
        suffix = ".".join(parts[idx:])
        parent = _get_binding_node(params, prefix)
        if not isinstance(parent, dict):
            continue
        if isinstance(parent.get("from"), str):
            source = str(parent["from"])
            if suffix:
                return f"{source}.{suffix}"
            return source
        if "literal" in parent:
            return "literal"
    return None


def _build_ancestor_map(steps: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    deps_by_step: Dict[str, List[str]] = {
        str(step.get("id")): list(step.get("depends_on", []) or [])
        for step in steps
        if step.get("id")
    }
    memo: Dict[str, Set[str]] = {}

    def ancestors(step_id: str) -> Set[str]:
        if step_id in memo:
            return memo[step_id]
        result: Set[str] = set()
        for dep in deps_by_step.get(step_id, []):
            if dep in result:
                continue
            result.add(dep)
            result.update(ancestors(dep))
        memo[step_id] = result
        return result

    for step_id in deps_by_step:
        ancestors(step_id)
    return memo


def _is_context_source_from_ancestors(
    context_source: str,
    step_id: str,
    steps_by_id: Dict[str, Dict[str, Any]],
    ancestors_by_step: Dict[str, Set[str]],
) -> bool:
    if not context_source:
        return False
    upstream_ids = ancestors_by_step.get(step_id, set())
    if not upstream_ids:
        return False

    for upstream_id in upstream_ids:
        upstream = steps_by_id.get(upstream_id)
        if not upstream:
            continue
        for output in upstream.get("outputs", []) or []:
            if not isinstance(output, dict):
                continue
            target = str(output.get("to_context") or "").strip()
            if not target:
                continue
            if context_source == target or context_source.startswith(f"{target}."):
                return True
    return False


def _derive_required_inputs_from_step_schemas(
    definition: WorkflowDefinition,
    capabilities_by_skill: Dict[str, AgentCapability],
) -> List[str]:
    """Infer required workflow inputs by inspecting each step's required skill params."""
    steps = [step.model_dump() for step in definition.steps]
    steps_by_id = {str(step.get("id")): step for step in steps if step.get("id")}
    ancestors_by_step = _build_ancestor_map(steps)
    required_inputs: Set[str] = set()

    for step in definition.steps:
        step_id = step.id
        cap = capabilities_by_skill.get(step.skill_id)
        if not cap or not isinstance(cap.input_schema, dict):
            continue

        required_paths = _extract_required_schema_paths(cap.input_schema)
        params_spec = step.params or {}
        for required_path in required_paths:
            source = _resolve_required_binding_source(params_spec, required_path)
            if not source:
                continue
            if source == "literal":
                continue
            if source.startswith("step."):
                continue
            if source.startswith("input."):
                path = source[len("input.") :].strip()
                if path:
                    required_inputs.add(path)
                continue
            if source.startswith("context."):
                context_path = source[len("context.") :].strip()
                if not context_path:
                    continue
                if _is_context_source_from_ancestors(
                    context_source=context_path,
                    step_id=step_id,
                    steps_by_id=steps_by_id,
                    ancestors_by_step=ancestors_by_step,
                ):
                    continue
                required_inputs.add(f"context.{context_path}")

    return sorted(required_inputs)


def _validate_dependencies(step_ids: List[str], steps: List[Dict[str, Any]]) -> None:
    id_set = set(step_ids)
    for step in steps:
        for dep in step.get("depends_on", []) or []:
            if dep not in id_set:
                raise WorkflowCompileError(f"Unknown depends_on reference '{dep}' in step '{step.get('id')}'")


def _detect_cycles(step_ids: List[str], steps: List[Dict[str, Any]]) -> None:
    graph: Dict[str, List[str]] = {}
    for step in steps:
        graph[step["id"]] = list(step.get("depends_on", []) or [])

    visiting: Set[str] = set()
    visited: Set[str] = set()

    def dfs(node: str) -> None:
        if node in visiting:
            raise WorkflowCompileError(f"Dependency cycle detected at step '{node}'")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        visiting.remove(node)
        visited.add(node)

    for node in step_ids:
        dfs(node)


def compile_workflow(
    raw: Dict[str, Any],
    source_path: Path,
    capabilities_by_skill: Optional[Dict[str, AgentCapability]] = None,
    strict: bool = True,
) -> CompiledWorkflow:
    """Compile a workflow YAML mapping into a validated `CompiledWorkflow`."""
    definition = WorkflowDefinition.model_validate(raw)

    if not definition.steps:
        raise WorkflowCompileError(f"Workflow '{definition.id}' has no steps")

    step_ids = [step.id for step in definition.steps]
    if len(step_ids) != len(set(step_ids)):
        raise WorkflowCompileError(f"Workflow '{definition.id}' has duplicate step IDs")

    steps_raw = [step.model_dump() for step in definition.steps]
    _validate_dependencies(step_ids, steps_raw)
    _detect_cycles(step_ids, steps_raw)

    compiled_patterns: List[CompiledPattern] = []
    for pattern in definition.matching.patterns:
        compiled_patterns.append(_compile_pattern(pattern))

    required_input_paths = list(definition.inputs.required or [])
    warnings: List[str] = []

    refs: List[Tuple[str, bool]] = []
    for step in definition.steps:
        _extract_input_binding_refs(step.params, refs)
    optional_inputs = set(definition.inputs.optional or [])
    for path, is_optional in refs:
        if not path:
            continue
        if is_optional or path in optional_inputs:
            continue
        if path not in required_input_paths:
            required_input_paths.append(path)

    if capabilities_by_skill is not None:
        inferred_required = _derive_required_inputs_from_step_schemas(definition, capabilities_by_skill)
        for path in inferred_required:
            if path not in required_input_paths:
                required_input_paths.append(path)

        for step in definition.steps:
            if step.skill_id not in capabilities_by_skill:
                message = (
                    f"Workflow '{definition.id}' step '{step.id}' references unknown skill "
                    f"'{step.skill_id}'"
                )
                if strict:
                    raise WorkflowCompileError(message)
                warnings.append(message)

    return CompiledWorkflow(
        definition=definition,
        source_path=source_path,
        compiled_patterns=compiled_patterns,
        required_input_paths=sorted(set(required_input_paths)),
        step_ids=step_ids,
        warnings=warnings,
    )
