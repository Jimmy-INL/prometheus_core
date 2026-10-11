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

"""Typed parameter binding for workflow step execution."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def get_path(data: Any, path: str) -> Any:
    if not path:
        return data
    if isinstance(data, dict) and path in data:
        return data[path]
    current = data
    for token in path.split("."):
        if isinstance(current, dict):
            if token not in current:
                return None
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                return None
            idx = int(token)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        return None
    return current


def set_path(data: Dict[str, Any], path: str, value: Any) -> None:
    if "." not in path:
        data[path] = value
        return
    current = data
    parts = path.split(".")
    for token in parts[:-1]:
        if token not in current or not isinstance(current[token], dict):
            current[token] = {}
        current = current[token]
    current[parts[-1]] = value


def resolve_source(
    source: str,
    state: Dict[str, Any],
) -> Any:
    if source.startswith("input."):
        return get_path(state.get("input", {}), source[len("input.") :])
    if source.startswith("context."):
        return get_path(state.get("context", {}), source[len("context.") :])
    if source.startswith("step."):
        return get_path(state.get("steps", {}), source[len("step.") :])
    return None


def resolve_binding_node(
    node: Any,
    state: Dict[str, Any],
) -> Tuple[Any, bool]:
    """Resolve a binding node. Returns (value, included)."""
    if isinstance(node, dict):
        if "from" in node:
            value = resolve_source(str(node.get("from")), state)
            optional = bool(node.get("optional", False))
            if value is None and optional:
                return None, False
            return value, value is not None
        if "literal" in node:
            return node.get("literal"), True

        out: Dict[str, Any] = {}
        for key, value in node.items():
            resolved, include = resolve_binding_node(value, state)
            if include:
                out[key] = resolved
        return out, True

    if isinstance(node, list):
        values = []
        for item in node:
            resolved, include = resolve_binding_node(item, state)
            if include:
                values.append(resolved)
        return values, True

    return node, True


def resolve_step_params(
    params_spec: Dict[str, Any],
    input_params: Dict[str, Any],
    context: Dict[str, Any],
    step_results: Dict[str, Any],
) -> Dict[str, Any]:
    state = {
        "input": input_params,
        "context": context,
        "steps": step_results,
    }
    resolved, _ = resolve_binding_node(params_spec or {}, state)
    if isinstance(resolved, dict):
        return resolved
    return {}
