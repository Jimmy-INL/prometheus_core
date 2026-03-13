"""Workflow registry with compile-time validation and atomic refresh."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import yaml

from .compiler import WorkflowCompileError, compile_workflow
from .schema import CompiledWorkflow

if TYPE_CHECKING:
    from capability_cache import AgentCapability
else:
    AgentCapability = Any


def _flatten_schema_properties(schema: Dict[str, Any], prefix: str = "") -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return result
    for key, prop in (schema.get("properties", {}) or {}).items():
        path = f"{prefix}{key}"
        if isinstance(prop, dict):
            result[path] = prop
            is_object = prop.get("type") == "object" or "properties" in prop
            if is_object:
                result.update(_flatten_schema_properties(prop, prefix=f"{path}."))
    return result


def _get_param_path(data: Dict[str, Any], path: str) -> Any:
    if path in data:
        return data[path]
    current: Any = data
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _has_param_path(data: Dict[str, Any], path: str) -> bool:
    value = _get_param_path(data, path)
    if value is None and path.startswith("context."):
        value = data.get(path.split(".", 1)[1])
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _append_unit_to_description(description: str, unit: Optional[str]) -> str:
    """Ensure UI description consistently includes unit hints when available."""
    text = str(description or "").strip()
    normalized_unit = str(unit or "").strip()
    if not normalized_unit:
        return text

    if text:
        try:
            # Detect standalone unit mentions like "MPa", "n/cm^2/s", "(C)".
            unit_pattern = rf"(?<!\w){re.escape(normalized_unit)}(?!\w)"
            if re.search(unit_pattern, text, flags=re.IGNORECASE):
                return text
            if re.search(rf"unit\s*:\s*{re.escape(normalized_unit)}", text, flags=re.IGNORECASE):
                return text
        except re.error:
            if normalized_unit.lower() in text.lower():
                return text

        return f"{text} Unit: {normalized_unit}."

    return f"Unit: {normalized_unit}."


@dataclass
class WorkflowSnapshot:
    """Immutable registry snapshot."""

    by_key: Dict[str, CompiledWorkflow]
    by_id: Dict[str, List[CompiledWorkflow]]
    checksum: str
    loaded_at: str
    errors: List[str]


class WorkflowRegistry:
    """Runtime registry for versioned workflow templates."""

    def __init__(self, workflows_dir: str, strict: bool = False):
        self.workflows_dir = Path(workflows_dir)
        self.strict = strict
        self._snapshot = WorkflowSnapshot(
            by_key={},
            by_id={},
            checksum="",
            loaded_at="",
            errors=[],
        )

    @property
    def snapshot(self) -> WorkflowSnapshot:
        return self._snapshot

    def list_all(self) -> List[CompiledWorkflow]:
        values = list(self._snapshot.by_key.values())
        values.sort(key=lambda item: (item.definition.id, item.definition.version))
        return values

    def get(self, workflow_id: str, version: Optional[str] = None) -> Optional[CompiledWorkflow]:
        candidates = self._snapshot.by_id.get(workflow_id, [])
        if not candidates:
            return None
        if version is None:
            # Highest lexical version as deterministic fallback.
            return sorted(candidates, key=lambda wf: wf.definition.version, reverse=True)[0]
        for item in candidates:
            if item.definition.version == version:
                return item
        return None

    def get_catalog(self) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        for workflow in self.list_all():
            ui = workflow.definition.ui
            metadata = workflow.definition.metadata
            cards.append(
                {
                    "id": workflow.definition.id,
                    "version": workflow.definition.version,
                    "display_name": ui.display_name or workflow.definition.name,
                    "summary": ui.summary or workflow.definition.description,
                    "category": ui.category or "General",
                    "requires_approval": bool(metadata.requires_approval),
                    "estimated_duration_seconds": metadata.estimated_duration_seconds,
                }
            )
        cards.sort(key=lambda item: (item["category"], item["display_name"], item["id"]))
        return cards

    def build_input_form(
        self,
        workflow_id: str,
        version: Optional[str],
        capabilities_by_skill: Dict[str, AgentCapability],
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        workflow = self.get(workflow_id, version=version)
        if workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' not found")

        merged = dict(params or {})
        ctx = dict(context or {})
        if ctx:
            merged.setdefault("context", {})
            if isinstance(merged["context"], dict):
                for key, value in ctx.items():
                    merged["context"].setdefault(key, value)

        # Aggregate schema metadata from all referenced capabilities.
        properties: Dict[str, Dict[str, Any]] = {}
        for step in workflow.definition.steps:
            cap = capabilities_by_skill.get(step.skill_id)
            if not cap:
                continue
            properties.update(_flatten_schema_properties(cap.input_schema))

        fields: List[Dict[str, Any]] = []
        for path in workflow.required_input_paths:
            if _has_param_path(merged, path):
                continue

            override = workflow.definition.ui.input_overrides.get(path)
            prop = properties.get(path)
            if not prop and "." in path:
                prop = properties.get(path.split(".", 1)[1])
            prop = prop or {}

            label = (
                (override.label if override else None)
                or prop.get("title")
                or path.split(".")[-1].replace("_", " ").title()
            )
            description = (
                (override.description if override else None)
                or prop.get("description")
                or f"Provide value for {path}"
            )
            unit = (
                (override.unit if override and override.unit else None)
                or prop.get("unit")
                or prop.get("x_unit")
                or prop.get("x-unit")
            )
            description = _append_unit_to_description(description, unit)
            field_type = (
                (override.type if override else None)
                or prop.get("type")
                or "text"
            )
            enum = prop.get("enum") if isinstance(prop, dict) else None
            source = (
                "workflow_override"
                if override and (override.label or override.description or override.type)
                else ("agent_card" if prop else "fallback")
            )
            fields.append(
                {
                    "field": path,
                    "label": label,
                    "description": description,
                    "type": field_type,
                    "required": True,
                    "options": (override.options if override and override.options else enum),
                    "unit": unit,
                    "source": source,
                }
            )

        return {
            "workflow_id": workflow.definition.id,
            "workflow_version": workflow.definition.version,
            "fields": fields,
        }

    def refresh(self, capabilities: List[AgentCapability]) -> Dict[str, Any]:
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}

        files = sorted(self.workflows_dir.glob("*.yaml")) + sorted(self.workflows_dir.glob("*.yml"))
        by_key: Dict[str, CompiledWorkflow] = {}
        by_id: Dict[str, List[CompiledWorkflow]] = {}
        errors: List[str] = []

        checksum_parts: List[str] = []
        for path in files:
            raw_text = path.read_text(encoding="utf-8")
            stat = path.stat()
            checksum_parts.append(
                f"{path}:{stat.st_mtime_ns}:{hashlib.sha256(raw_text.encode('utf-8')).hexdigest()}"
            )
            try:
                data = yaml.safe_load(raw_text) or {}
                compiled = compile_workflow(
                    raw=data,
                    source_path=path,
                    capabilities_by_skill=capabilities_by_skill,
                    strict=self.strict,
                )
            except (WorkflowCompileError, Exception) as exc:
                errors.append(f"{path.name}: {exc}")
                continue

            key = compiled.key
            if key in by_key:
                errors.append(f"{path.name}: duplicate workflow key '{key}'")
                continue
            by_key[key] = compiled
            by_id.setdefault(compiled.definition.id, []).append(compiled)

        for workflow_id, items in by_id.items():
            by_id[workflow_id] = sorted(items, key=lambda wf: wf.definition.version, reverse=True)

        checksum = hashlib.sha256("\n".join(sorted(checksum_parts)).encode("utf-8")).hexdigest()
        next_snapshot = WorkflowSnapshot(
            by_key=by_key,
            by_id=by_id,
            checksum=checksum,
            loaded_at=datetime.now(timezone.utc).isoformat(),
            errors=errors,
        )
        self._snapshot = next_snapshot

        return {
            "count": len(by_key),
            "errors": errors,
            "checksum": checksum,
        }


_workflow_registry: Optional[WorkflowRegistry] = None


def get_workflow_registry() -> WorkflowRegistry:
    global _workflow_registry
    if _workflow_registry is None:
        workflows_dir = os.getenv("WORKFLOW_LIBRARY_DIR", "/app/workflows")
        strict = os.getenv("WORKFLOW_LIBRARY_STRICT", "false").lower() in {"1", "true", "yes"}
        _workflow_registry = WorkflowRegistry(workflows_dir=workflows_dir, strict=strict)
    return _workflow_registry
