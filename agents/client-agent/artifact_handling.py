"""Declarative artifact catalog and artifact-input resolution helpers."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from param_schema import get_nested_value, set_nested_value

ARTIFACT_REF_KEYS = ("x_artifact_ref", "x-artifact-ref", "artifact_ref")
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}\b"
)


def normalize_artifact_name(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def summarize_artifacts_for_context(
    artifacts: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build compact artifact metadata for planning/execution context."""
    summary: List[Dict[str, Any]] = []
    seen_ids = set()
    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("artifact_id") or "").strip()
        name = str(artifact.get("name") or "").strip()
        if not artifact_id or not name or artifact_id in seen_ids:
            continue
        seen_ids.add(artifact_id)
        summary.append(
            {
                "artifact_id": artifact_id,
                "name": name,
                "description": str(artifact.get("description") or "")[:280],
                "uri": str(artifact.get("uri") or ""),
                "mime_type": artifact.get("mime_type"),
                "size_bytes": artifact.get("size_bytes"),
                "producer_agent_id": artifact.get("producer_agent_id"),
                "created_at": artifact.get("created_at"),
                "tags": artifact.get("tags") or [],
                "metadata": artifact.get("metadata") or {},
            }
        )
    return summary


def merge_artifacts_into_context(
    existing_context: Optional[Dict[str, Any]],
    artifacts: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Merge artifact catalogs into context without dropping prior entries."""
    merged = dict(existing_context or {})
    # Drop transient per-turn keys — set fresh by _execute() each turn.
    merged.pop("newly_uploaded_artifact_ids", None)
    merged.pop("received_files", None)
    current_catalog = summarize_artifacts_for_context((existing_context or {}).get("artifacts"))
    next_catalog = summarize_artifacts_for_context(artifacts)
    existing_ids = {item["artifact_id"] for item in current_catalog}
    combined = current_catalog + [item for item in next_catalog if item["artifact_id"] not in existing_ids]
    if combined:
        merged["artifacts"] = combined
    return merged


def merge_artifact_catalogs(
    existing_artifacts: Optional[List[Dict[str, Any]]],
    incoming_artifacts: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Merge two external artifact catalogs using artifact_id as the key."""
    merged: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in summarize_artifacts_for_context(existing_artifacts) + summarize_artifacts_for_context(incoming_artifacts):
        artifact_id = item["artifact_id"]
        if artifact_id in seen_ids:
            continue
        seen_ids.add(artifact_id)
        merged.append(item)
    return merged


def _build_artifact_indexes(
    context: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    artifact_by_id: Dict[str, Dict[str, Any]] = {}
    artifact_by_name: Dict[str, str] = {}
    for item in summarize_artifacts_for_context((context or {}).get("artifacts")):
        artifact_by_id[item["artifact_id"]] = item
        artifact_by_name[normalize_artifact_name(item["name"])] = item["artifact_id"]
    return artifact_by_id, artifact_by_name


def _resolve_artifact_identifier(
    value: Any,
    artifact_by_id: Dict[str, Dict[str, Any]],
    artifact_by_name: Dict[str, str],
) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in artifact_by_id:
        return text
    return artifact_by_name.get(normalize_artifact_name(text))


def _artifact_binding_mode(prop: Dict[str, Any]) -> Optional[str]:
    for key in ARTIFACT_REF_KEYS:
        raw = prop.get(key)
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if text in {"single", "multiple"}:
            return text
        if text in {"true", "1", "yes"}:
            return "single"
    return None


def extract_artifact_field_paths(
    schema: Dict[str, Any],
    prefix: str = "",
) -> Dict[str, str]:
    """Return dotted artifact-capable field paths declared in an input schema."""
    result: Dict[str, str] = {}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return result

    for key, prop in (schema.get("properties", {}) or {}).items():
        path = f"{prefix}{key}"
        if not isinstance(prop, dict):
            continue
        mode = _artifact_binding_mode(prop)
        if mode:
            result[path] = mode
        is_object = prop.get("type") == "object" or "properties" in prop
        if is_object:
            result.update(extract_artifact_field_paths(prop, prefix=f"{path}."))
    return result


def bind_produced_artifacts(
    params: Dict[str, Any],
    input_schema: Optional[Dict[str, Any]],
    produced_artifact_ids: List[str],
) -> Dict[str, Any]:
    """Fill unfilled artifact-reference params from earlier sequential steps.

    In a sequential plan, a downstream skill's `x_artifact_ref` inputs are
    typically produced by an upstream step in the same plan (e.g. create an
    SVG, then convert it to PNG). The planner defers these at planning time
    (`deferred_runtime_paths`); this binds them just before invocation:
    single-mode paths get the most recently produced artifact id, multi-mode
    paths get all of them. Already-filled paths are left untouched.
    """
    if not produced_artifact_ids or not isinstance(input_schema, dict):
        return params
    artifact_paths = extract_artifact_field_paths(input_schema)
    if not artifact_paths:
        return params

    resolved = dict(params or {})
    for path, mode in artifact_paths.items():
        if get_nested_value(resolved, path) is not None:
            continue
        if mode == "multiple":
            set_nested_value(resolved, path, list(produced_artifact_ids))
        else:
            set_nested_value(resolved, path, produced_artifact_ids[-1])
    return resolved


def resolve_artifact_inputs(
    params: Dict[str, Any],
    query: str,
    context: Optional[Dict[str, Any]],
    input_schemas: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve declared artifact-reference inputs from the conversation artifact catalog."""
    artifact_paths: Dict[str, str] = {}
    for schema in input_schemas:
        artifact_paths.update(extract_artifact_field_paths(schema))
    if not artifact_paths:
        return params

    artifact_by_id, artifact_by_name = _build_artifact_indexes(context)
    if not artifact_by_id:
        return params

    resolved = dict(params or {})
    for path, mode in artifact_paths.items():
        existing = get_nested_value(resolved, path)
        if mode == "multiple":
            if isinstance(existing, list):
                resolved_list: List[str] = []
                for item in existing:
                    artifact_id = _resolve_artifact_identifier(item, artifact_by_id, artifact_by_name)
                    if artifact_id and artifact_id not in resolved_list:
                        resolved_list.append(artifact_id)
                if resolved_list:
                    set_nested_value(resolved, path, resolved_list)
        else:
            artifact_id = _resolve_artifact_identifier(existing, artifact_by_id, artifact_by_name)
            if artifact_id:
                set_nested_value(resolved, path, artifact_id)

    matched_ids: List[str] = []
    q = str(query or "")
    for uuid_match in UUID_PATTERN.findall(q):
        if uuid_match in artifact_by_id and uuid_match not in matched_ids:
            matched_ids.append(uuid_match)
    q_normalized = normalize_artifact_name(q)
    if q_normalized:
        for normalized_name, artifact_id in artifact_by_name.items():
            if normalized_name and normalized_name in q_normalized and artifact_id not in matched_ids:
                matched_ids.append(artifact_id)

    if matched_ids:
        for path, mode in artifact_paths.items():
            if get_nested_value(resolved, path) is not None:
                continue
            if mode == "multiple":
                set_nested_value(resolved, path, list(matched_ids))
            else:
                set_nested_value(resolved, path, matched_ids[0])

    # Conservative auto-binding for newly-uploaded artifacts.
    # Only bind when there is exactly 1 newly-uploaded artifact AND
    # exactly 1 still-unfilled x_artifact_ref field.
    newly_uploaded = list((context or {}).get("newly_uploaded_artifact_ids") or [])
    if newly_uploaded:
        unfilled_paths = [
            path for path in artifact_paths if get_nested_value(resolved, path) is None
        ]
        valid_candidates = [aid for aid in newly_uploaded if aid in artifact_by_id]
        if len(valid_candidates) == 1 and len(unfilled_paths) == 1:
            path = unfilled_paths[0]
            mode = artifact_paths[path]
            if mode == "multiple":
                set_nested_value(resolved, path, valid_candidates)
            else:
                set_nested_value(resolved, path, valid_candidates[0])

    return resolved
