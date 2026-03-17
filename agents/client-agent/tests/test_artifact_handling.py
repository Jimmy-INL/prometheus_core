"""Unit tests for declarative artifact catalog and input resolution helpers."""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from artifact_handling import merge_artifact_catalogs, resolve_artifact_inputs


def test_merge_artifact_catalogs_preserves_existing_and_incoming() -> None:
    existing = [
        {"artifact_id": "a-1", "name": "Original CAD", "uri": "file:///tmp/original.step"},
    ]
    incoming = [
        {"artifact_id": "a-2", "name": "New Mesh", "uri": "file:///tmp/new.msh"},
    ]

    merged = merge_artifact_catalogs(existing, incoming)

    assert [item["artifact_id"] for item in merged] == ["a-1", "a-2"]


def test_resolve_artifact_inputs_uses_declared_schema_paths() -> None:
    schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "object",
                "properties": {
                    "svg_reference": {
                        "type": "string",
                        "x_artifact_ref": "single",
                    }
                },
            }
        },
    }
    context = {
        "artifacts": [
            {
                "artifact_id": "svg-123",
                "name": "demo diagram",
                "uri": "file:///tmp/demo.svg",
            }
        ]
    }

    resolved = resolve_artifact_inputs(
        params={},
        query="Convert the demo diagram to png",
        context=context,
        input_schemas=[schema],
    )

    assert resolved["source"]["svg_reference"] == "svg-123"


def test_resolve_artifact_inputs_normalizes_explicit_declared_values() -> None:
    schema = {
        "type": "object",
        "properties": {
            "attachments": {
                "type": "array",
                "items": {"type": "string"},
                "x_artifact_ref": "multiple",
            }
        },
    }
    context = {
        "artifacts": [
            {"artifact_id": "doc-1", "name": "Alpha Report", "uri": "file:///tmp/a.pdf"},
            {"artifact_id": "doc-2", "name": "Beta Report", "uri": "file:///tmp/b.pdf"},
        ]
    }

    resolved = resolve_artifact_inputs(
        params={"attachments": ["beta report", "doc-1"]},
        query="",
        context=context,
        input_schemas=[schema],
    )

    assert resolved["attachments"] == ["doc-2", "doc-1"]
