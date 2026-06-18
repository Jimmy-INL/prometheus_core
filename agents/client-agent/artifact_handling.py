"""Declarative artifact catalog and artifact-input resolution helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from param_schema import extract_required_param_paths, get_nested_value, set_nested_value

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


@dataclass
class ChainRequiredPaths:
    """Aggregated required-input paths across a (possibly sequential) skill chain."""

    user_paths: Set[str]
    runtime_paths: Set[str]
    deferred_paths: Set[str]


def collect_chain_required_paths(
    capabilities: Sequence[Any],
    workflow_type: Optional[str],
) -> ChainRequiredPaths:
    """Compute user-required and runtime-required paths for a skill chain.

    Sequential dataflow: artifact-reference inputs of downstream skills are
    produced by earlier steps at runtime. They cannot exist at planning time,
    so they are deferred — neither asked from the user nor counted as
    missing. This is the single source of that rule; the planner's
    requirement status, the planning flow, and follow-up recomputation all
    derive from it.

    ``capabilities`` is the chain's capabilities in execution order (None
    entries for unknown skills are skipped, preserving positions).
    """
    user_paths: Set[str] = set()
    runtime_paths: Set[str] = set()
    deferred_paths: Set[str] = set()
    for index, capability in enumerate(capabilities):
        input_schema = getattr(capability, "input_schema", None)
        if not isinstance(input_schema, dict):
            continue
        user_required = set(extract_required_param_paths(input_schema))
        all_required = set(extract_required_param_paths(input_schema, include_internal=True))
        if workflow_type == "sequential" and index > 0:
            artifact_paths = set(extract_artifact_field_paths(input_schema))
            deferred = (user_required | all_required) & artifact_paths
            deferred_paths |= deferred
            user_required -= deferred
            all_required -= deferred
        user_paths |= user_required
        runtime_paths |= all_required - user_required
    return ChainRequiredPaths(user_paths, runtime_paths, deferred_paths)


_BIND_STOPWORDS = {
    "a", "an", "and", "artifact", "artifacts", "file", "for", "from", "id", "ids",
    "input", "of", "or", "output", "the", "this", "to", "with",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _binding_tokens(*texts: Any) -> set:
    tokens: set = set()
    for text in texts:
        if text is None:
            continue
        if isinstance(text, (list, tuple)):
            tokens |= _binding_tokens(*text)
            continue
        tokens |= set(_TOKEN_RE.findall(str(text).lower()))
    return tokens - _BIND_STOPWORDS


def _param_mime_hints(prop: Dict[str, Any]) -> List[str]:
    raw = prop.get("x_artifact_mime") or prop.get("x-artifact-mime") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _score_artifact_for_param(
    path: str,
    prop: Dict[str, Any],
    artifact: Dict[str, Any],
    order_index: int,
) -> Optional[float]:
    """Score how well a produced artifact fits an artifact-ref param.

    Returns None when an explicit ``x_artifact_mime`` hint on the param
    disqualifies the artifact outright.
    """
    mime = str(artifact.get("mime_type") or "").strip().lower()
    hints = _param_mime_hints(prop)
    score = 0.0
    if hints:
        if mime and any(mime == hint or mime.startswith(hint) for hint in hints):
            score += 100.0
        else:
            return None

    name = str(artifact.get("name") or "")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    artifact_tokens = _binding_tokens(
        name, artifact.get("description"), mime, artifact.get("tags"), extension
    )
    param_tokens = _binding_tokens(path, prop.get("description"))
    score += 10.0 * len(param_tokens & artifact_tokens)

    # Recency: prefer later steps; within equal description fit, the primary
    # (first-emitted) artifact of a step beats its side artifacts.
    score += float(artifact.get("_step") or 0) * 2.0
    if artifact.get("_primary"):
        score += 1.0
    # Stable tiebreak toward more recently emitted artifacts.
    score += order_index * 0.01
    return score


def _default_chain_artifact(produced_artifacts: List[Dict[str, Any]]) -> Optional[str]:
    """The primary (first-emitted) artifact of the most recent producing step."""
    if not produced_artifacts:
        return None
    last_step = max(int(a.get("_step") or 0) for a in produced_artifacts)
    for artifact in produced_artifacts:
        if int(artifact.get("_step") or 0) == last_step and artifact.get("_primary"):
            return str(artifact.get("artifact_id") or "") or None
    return str(produced_artifacts[-1].get("artifact_id") or "") or None


def bind_produced_artifacts(
    params: Dict[str, Any],
    input_schema: Optional[Dict[str, Any]],
    produced_artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Bind artifact-reference params to artifacts produced by earlier steps.

    In a sequential plan, a downstream skill's `x_artifact_ref` inputs refer
    to the chain's own dataflow (e.g. revise a CAD model, then mesh *it*).
    Planning-time artifact resolution binds catalog artifacts for the FIRST
    step (correct: "revise the valve" needs the existing valve), but the
    extracted params are shared by every step — so once an upstream step has
    produced artifacts, an inherited planning-time value on a later step is
    stale by construction.

    Single-mode paths are therefore OVERRIDDEN (unless the current value is
    itself chain-produced) with the best-matching produced artifact:
    each candidate is scored by the param's optional ``x_artifact_mime``
    hint, token overlap between the param's name/description and the
    artifact's name/description/mime/tags/extension, and recency (later
    steps win; a step's first-emitted artifact beats its side artifacts).
    So "Exodus mesh artifact to post-process" selects the .e mesh even when
    a visualization artifact was emitted first, and two params with distinct
    descriptions can each bind to a different upstream step's output.

    ``produced_artifacts`` entries carry artifact_id/name/description/
    mime_type/tags plus ``_step`` (producing step index) and ``_primary``
    (first-emitted in its step). Multi-mode paths are filled (only when
    empty) with every produced id, in order.
    """
    if not produced_artifacts or not isinstance(input_schema, dict):
        return params
    artifact_paths = extract_artifact_field_paths(input_schema)
    if not artifact_paths:
        return params

    properties = input_schema.get("properties", {}) or {}
    produced_ids = [str(a.get("artifact_id") or "") for a in produced_artifacts]
    fallback = _default_chain_artifact(produced_artifacts)

    def _prop_for(path: str) -> Dict[str, Any]:
        node: Any = {"properties": properties}
        for part in path.split("."):
            node = (node.get("properties", {}) or {}).get(part, {})
            if not isinstance(node, dict):
                return {}
        return node

    resolved = dict(params or {})
    for path, mode in artifact_paths.items():
        current = get_nested_value(resolved, path)
        if mode == "multiple":
            if current is None:
                set_nested_value(resolved, path, [aid for aid in produced_ids if aid])
            continue
        if current is not None and str(current) in produced_ids:
            continue  # already bound to chain output (or planner anticipated it)

        prop = _prop_for(path)
        best_id: Optional[str] = None
        best_score: Optional[float] = None
        for order_index, artifact in enumerate(produced_artifacts):
            artifact_id = str(artifact.get("artifact_id") or "")
            if not artifact_id:
                continue
            score = _score_artifact_for_param(path, prop, artifact, order_index)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_id = artifact_id
        chosen = best_id or fallback
        if chosen:
            set_nested_value(resolved, path, chosen)
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
