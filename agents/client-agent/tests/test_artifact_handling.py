"""Unit tests for declarative artifact catalog and input resolution helpers."""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from artifact_handling import merge_artifact_catalogs, merge_artifacts_into_context, resolve_artifact_inputs


def test_merge_artifact_catalogs_preserves_existing_and_incoming() -> None:
    existing = [
        {"artifact_id": "a-1", "name": "Original CAD", "uri": "file:///tmp/original.step"},
    ]
    incoming = [
        {
            "artifact_id": "a-2",
            "name": "New Mesh",
            "uri": "file:///tmp/new.msh",
            "metadata": {"deeplynx_file_id": 42},
        },
    ]

    merged = merge_artifact_catalogs(existing, incoming)

    assert [item["artifact_id"] for item in merged] == ["a-1", "a-2"]
    assert merged[1]["metadata"] == {"deeplynx_file_id": 42}


def test_merge_artifacts_into_context_drops_transient_upload_keys() -> None:
    merged = merge_artifacts_into_context(
        {
            "newly_uploaded_artifact_ids": ["upload-1"],
            "received_files": [{"name": "stale.ifc"}],
            "other": "keep",
        },
        [],
    )

    assert "newly_uploaded_artifact_ids" not in merged
    assert "received_files" not in merged
    assert merged["other"] == "keep"


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


def test_collect_chain_required_paths_defers_downstream_artifact_refs() -> None:
    from types import SimpleNamespace

    from artifact_handling import collect_chain_required_paths

    revise = SimpleNamespace(
        input_schema={
            "type": "object",
            "properties": {"artifact_id": {"type": "string", "x_artifact_ref": "single"}},
            "required": ["artifact_id"],
        }
    )
    mesh = SimpleNamespace(
        input_schema={
            "type": "object",
            "properties": {
                "mesh_artifact_id": {"type": "string", "x_artifact_ref": "single"},
                "element_size_mm": {"type": "number"},
            },
            "required": ["mesh_artifact_id", "element_size_mm"],
        }
    )

    chain = collect_chain_required_paths([revise, mesh], "sequential")
    # The first step's artifact input is a genuine user requirement; the
    # downstream step's is runtime-produced and deferred.
    assert chain.user_paths == {"artifact_id", "element_size_mm"}
    assert chain.deferred_paths == {"mesh_artifact_id"}

    # Outside sequential chains nothing is deferred.
    chain = collect_chain_required_paths([revise, mesh], "parallel")
    assert chain.user_paths == {"artifact_id", "mesh_artifact_id", "element_size_mm"}
    assert chain.deferred_paths == set()
