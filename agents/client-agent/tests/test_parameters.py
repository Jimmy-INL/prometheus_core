"""Tests for shared parameter-requirement helpers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from orchestrator import parameters  # noqa: E402


def _fake_cache(monkeypatch, capabilities_by_skill) -> None:
    async def fake_get(skill_id):
        return capabilities_by_skill.get(skill_id)

    monkeypatch.setattr(
        parameters,
        "get_capability_cache",
        lambda: SimpleNamespace(get_capability_by_skill_id=fake_get),
    )


def test_resolve_user_required_params_defers_sequential_artifact_refs(monkeypatch) -> None:
    """Follow-up recomputation must not resurface runtime-produced artifact
    refs the planner deferred, or the user gets asked for ids that do not
    exist until execution."""
    _fake_cache(
        monkeypatch,
        {
            "revise_cad": SimpleNamespace(
                input_schema={
                    "type": "object",
                    "properties": {"artifact_id": {"type": "string", "x_artifact_ref": "single"}},
                    "required": ["artifact_id"],
                }
            ),
            "mesh": SimpleNamespace(
                input_schema={
                    "type": "object",
                    "properties": {
                        "mesh_artifact_id": {"type": "string", "x_artifact_ref": "single"},
                        "element_size_mm": {"type": "number"},
                    },
                    "required": ["mesh_artifact_id", "element_size_mm"],
                }
            ),
        },
    )
    routing_decision = {
        "primary_skill": "revise_cad",
        "supporting_skills": ["mesh"],
        "workflow_type": "sequential",
        "extracted_params": {},
    }

    required = asyncio.run(parameters.resolve_user_required_params(routing_decision))

    assert "mesh_artifact_id" not in required
    assert required == ["artifact_id", "element_size_mm"]


def test_compute_required_and_missing_applies_fallback(monkeypatch) -> None:
    _fake_cache(
        monkeypatch,
        {
            "analyze": SimpleNamespace(
                input_schema={
                    "type": "object",
                    "properties": {"material_id": {"type": "string"}},
                    "required": ["material_id"],
                }
            )
        },
    )
    routing_decision = {
        "primary_skill": "analyze",
        "supporting_skills": [],
        "workflow_type": "single",
        "extracted_params": {"material_id": "SS316"},
    }

    required, missing = asyncio.run(
        parameters.compute_required_and_missing(
            routing_decision,
            fallback_missing=["stored_param"],
        )
    )

    assert required == ["material_id"]
    # Everything required is provided, so the stored fallback wins.
    assert missing == ["stored_param"]

    routing_decision["extracted_params"] = {}
    _, missing = asyncio.run(parameters.compute_required_and_missing(routing_decision))
    assert missing == ["material_id"]
