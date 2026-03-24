"""Deterministic workflow matcher."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .schema import CompiledWorkflow


@dataclass
class WorkflowMatch:
    workflow_id: str
    workflow_version: str
    score: float
    method: str
    extracted_params: Dict[str, Any]
    priority: int
    required_satisfied: int


def _convert_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return text
    try:
        if "." in text:
            return float(text)
        return int(text)
    except Exception:
        return text


def _count_required_satisfied(required_paths: List[str], params: Dict[str, Any]) -> int:
    def get(path: str) -> Any:
        if path in params:
            return params[path]
        current: Any = params
        for token in path.split("."):
            if not isinstance(current, dict) or token not in current:
                return None
            current = current[token]
        return current

    count = 0
    for path in required_paths:
        value = get(path)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        count += 1
    return count


def match_workflows(
    query: str,
    workflows: List[CompiledWorkflow],
    min_score: float = 0.0,
) -> List[WorkflowMatch]:
    """Run deterministic pattern matching and return sorted candidates."""
    q = (query or "").strip()
    if not q:
        return []

    matches: List[WorkflowMatch] = []
    for workflow in workflows:
        priority = int(workflow.definition.matching.priority or 0)
        for pattern in workflow.compiled_patterns:
            result = pattern.regex.search(q)
            if not result:
                continue

            extracted: Dict[str, Any] = {}
            groups = result.groupdict() or {}
            for placeholder in pattern.placeholder_names:
                group_name = placeholder.replace(".", "_")
                if group_name not in groups:
                    continue
                raw = groups[group_name]
                if raw is None:
                    continue
                extracted[placeholder] = _convert_scalar(raw)

            required_satisfied = _count_required_satisfied(workflow.required_input_paths, extracted)
            score = (
                float(pattern.specificity)
                + float(priority) * 100.0
                + float(required_satisfied) * 20.0
            )
            if score < min_score:
                continue

            matches.append(
                WorkflowMatch(
                    workflow_id=workflow.definition.id,
                    workflow_version=workflow.definition.version,
                    score=score,
                    method="pattern",
                    extracted_params=extracted,
                    priority=priority,
                    required_satisfied=required_satisfied,
                )
            )

    # tie-break: score, priority, required satisfied, lexical workflow id
    matches.sort(
        key=lambda item: (
            -item.score,
            -item.priority,
            -item.required_satisfied,
            item.workflow_id,
        )
    )
    return matches


def top_match(query: str, workflows: List[CompiledWorkflow]) -> Optional[WorkflowMatch]:
    results = match_workflows(query=query, workflows=workflows)
    return results[0] if results else None
