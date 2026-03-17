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
        artifact_id = str(
            artifact.get("artifact_id")
            or artifact.get("artifactId")
            or artifact.get("id")
            or ""
        ).strip()
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
                "mime_type": artifact.get("mime_type") or artifact.get("mimeType"),
                "size_bytes": artifact.get("size_bytes") or artifact.get("sizeBytes"),
                "producer_agent_id": artifact.get("producer_agent_id") or artifact.get("producerAgentId"),
                "created_at": artifact.get("created_at") or artifact.get("createdAt"),
                "tags": artifact.get("tags") or [],
            }
        )
    return summary


def merge_artifacts_into_context(
    existing_context: Optional[Dict[str, Any]],
    artifacts: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Merge artifact catalogs into context without dropping prior entries."""
    merged = dict(existing_context or {})
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

    if not matched_ids:
        return resolved

    for path, mode in artifact_paths.items():
        if get_nested_value(resolved, path) is not None:
            continue
        if mode == "multiple":
            set_nested_value(resolved, path, list(matched_ids))
        else:
            set_nested_value(resolved, path, matched_ids[0])

    return resolved
