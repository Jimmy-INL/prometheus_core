"""Unit tests for LLM-mediated step-transition parameter mapping."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from orchestrator import runtime
from orchestrator.step_transition import resolve_step_transition_params


class _FakeLLM:
    """Captures prompts; returns canned content or raises."""

    def __init__(self, payload):
        self._payload = payload
        self.prompts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def medium(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if isinstance(self._payload, Exception):
            raise self._payload
        return SimpleNamespace(text=self._payload)


SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_id": {
            "type": "string",
            "x_artifact_ref": "single",
            "description": "Exodus mesh artifact to post-process.",
        },
        "element_size_mm": {
            "type": "number",
            "description": "Target element size in millimeters.",
        },
    },
    "required": ["artifact_id"],
}

PRODUCED = [
    {
        "artifact_id": "viz-1",
        "name": "preview.html",
        "description": "Interactive visualization preview",
        "mime_type": "text/html",
        "tags": [],
        "_step": 0,
        "_primary": True,
    },
    {
        "artifact_id": "mesh-1",
        "name": "valve_mesh.e",
        "description": "Exodus mesh of the valve",
        "mime_type": "application/x-exodus",
        "tags": [],
        "_step": 0,
        "_primary": False,
    },
]

CHAIN = [
    {
        "skill_id": "generate_mesh",
        "result_text": "Meshed the valve. Recommended element size: 2 mm for the analysis.",
        "artifacts": PRODUCED,
    }
]


def _capability(schema=SCHEMA):
    return SimpleNamespace(input_schema=schema, description="Post-process a mesh")


def _resolve(fake, params=None, *, chain=CHAIN, produced=PRODUCED, monkeypatch=None, query="mesh the valve then post-process it"):
    monkeypatch.setattr(runtime, "create_llm", lambda: fake)
    return asyncio.run(
        resolve_step_transition_params(
            skill_id="post_process",
            capability=_capability(),
            params=dict(params or {}),
            chain_steps=chain,
            produced_artifacts=produced,
            user_query=query,
            conversation_id=None,
        )
    )


def test_llm_binds_artifact_and_fills_param_from_step_text(monkeypatch) -> None:
    fake = _FakeLLM(json.dumps({"artifact_id": "mesh-1", "element_size_mm": "2"}))
    resolved = _resolve(fake, monkeypatch=monkeypatch)

    assert resolved["artifact_id"] == "mesh-1"
    assert resolved["element_size_mm"] == 2.0  # coerced to the schema type

    # The upstream step's prose output must be visible to the mapping LLM.
    assert "Recommended element size" in fake.prompts[0]
    assert "valve_mesh.e" in fake.prompts[0]


def test_invented_artifact_id_is_dropped_and_matcher_decides(monkeypatch) -> None:
    fake = _FakeLLM(json.dumps({"artifact_id": "made-up-id"}))
    resolved = _resolve(fake, monkeypatch=monkeypatch)

    # Deterministic fallback selects the description-matching mesh artifact.
    assert resolved["artifact_id"] == "mesh-1"


def test_llm_error_falls_back_to_deterministic_binding(monkeypatch) -> None:
    fake = _FakeLLM(RuntimeError("llm unavailable"))
    resolved = _resolve(fake, monkeypatch=monkeypatch)

    assert resolved["artifact_id"] == "mesh-1"


def test_unparseable_response_falls_back(monkeypatch) -> None:
    fake = _FakeLLM("sorry, I cannot help with that")
    resolved = _resolve(fake, monkeypatch=monkeypatch)

    assert resolved["artifact_id"] == "mesh-1"


def test_existing_non_artifact_value_is_not_overridden(monkeypatch) -> None:
    fake = _FakeLLM(json.dumps({"artifact_id": "mesh-1", "element_size_mm": 1}))
    resolved = _resolve(fake, params={"element_size_mm": 5}, monkeypatch=monkeypatch)

    assert resolved["element_size_mm"] == 5


def test_llm_may_bind_catalog_artifact_against_matcher_preference(monkeypatch) -> None:
    """An explicit, validated LLM choice of a pre-existing catalog artifact
    survives the deterministic pass that would otherwise rebind it."""
    fake = _FakeLLM(json.dumps({"artifact_id": "cat-9"}))
    params = {
        "artifacts": [
            {"artifact_id": "cat-9", "name": "original.step", "description": "User-uploaded original model"}
        ]
    }
    resolved = _resolve(fake, params=params, monkeypatch=monkeypatch)

    assert resolved["artifact_id"] == "cat-9"


def test_multiple_mode_filters_invalid_ids(monkeypatch) -> None:
    schema = {
        "type": "object",
        "properties": {
            "attachments": {
                "type": "array",
                "items": {"type": "string"},
                "x_artifact_ref": "multiple",
                "description": "Artifacts to attach.",
            }
        },
    }
    fake = _FakeLLM(json.dumps({"attachments": ["mesh-1", "bogus"]}))
    monkeypatch.setattr(runtime, "create_llm", lambda: fake)
    resolved = asyncio.run(
        resolve_step_transition_params(
            skill_id="report",
            capability=SimpleNamespace(input_schema=schema, description="Build report"),
            params={},
            chain_steps=CHAIN,
            produced_artifacts=PRODUCED,
            user_query="then build a report",
            conversation_id=None,
        )
    )

    assert resolved["attachments"] == ["mesh-1"]


def test_no_chain_steps_is_a_passthrough(monkeypatch) -> None:
    def _boom():
        raise AssertionError("LLM must not be called without completed steps")

    monkeypatch.setattr(runtime, "create_llm", _boom)
    resolved = asyncio.run(
        resolve_step_transition_params(
            skill_id="post_process",
            capability=_capability(),
            params={"element_size_mm": 5},
            chain_steps=[],
            produced_artifacts=[],
            user_query="anything",
            conversation_id=None,
        )
    )

    assert resolved == {"element_size_mm": 5}


def test_unknown_paths_and_enum_violations_are_dropped(monkeypatch) -> None:
    schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "x_artifact_ref": "single"},
            "format": {"type": "string", "enum": ["pdf", "html"]},
        },
    }
    fake = _FakeLLM(json.dumps({"format": "docx", "nonexistent_param": 1, "artifact_id": "mesh-1"}))
    monkeypatch.setattr(runtime, "create_llm", lambda: fake)
    resolved = asyncio.run(
        resolve_step_transition_params(
            skill_id="export",
            capability=SimpleNamespace(input_schema=schema, description="Export"),
            params={},
            chain_steps=CHAIN,
            produced_artifacts=PRODUCED,
            user_query="then export it",
            conversation_id=None,
        )
    )

    assert resolved["artifact_id"] == "mesh-1"
    assert "format" not in resolved
    assert "nonexistent_param" not in resolved
