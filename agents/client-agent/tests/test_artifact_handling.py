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


def _produced(step, primary, artifact_id, name, description="", mime_type=None, tags=None):
    return {
        "artifact_id": artifact_id,
        "name": name,
        "description": description,
        "mime_type": mime_type,
        "tags": tags or [],
        "_step": step,
        "_primary": primary,
    }


def test_bind_skips_viz_side_artifact_via_description_match() -> None:
    """A step emits a visualization first and the real output second; the
    downstream param's description must select the correct artifact."""
    from artifact_handling import bind_produced_artifacts

    schema = {
        "type": "object",
        "properties": {
            "artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
                "description": "Exodus mesh artifact to post-process.",
            }
        },
        "required": ["artifact_id"],
    }
    produced = [
        _produced(0, True, "viz-1", "preview.html", "Interactive visualization preview", "text/html"),
        _produced(0, False, "mesh-1", "valve_mesh.e", "Exodus mesh of the valve", "application/x-exodus"),
    ]

    resolved = bind_produced_artifacts({}, schema, produced)
    assert resolved["artifact_id"] == "mesh-1"


def test_bind_two_params_to_two_different_upstream_steps() -> None:
    """A third step consuming two artifacts binds each param to the matching
    upstream output, not both to the latest."""
    from artifact_handling import bind_produced_artifacts

    schema = {
        "type": "object",
        "properties": {
            "geometry_artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
                "description": "CAD geometry (STEP model) to analyze.",
            },
            "mesh_artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
                "description": "Exodus mesh artifact.",
            },
        },
        "required": ["geometry_artifact_id", "mesh_artifact_id"],
    }
    produced = [
        _produced(0, True, "cad-1", "valve.step", "Revised CAD model", "model/step"),
        _produced(1, True, "mesh-1", "valve_mesh.e", "Exodus mesh", "application/x-exodus"),
    ]

    resolved = bind_produced_artifacts({}, schema, produced)
    assert resolved["geometry_artifact_id"] == "cad-1"
    assert resolved["mesh_artifact_id"] == "mesh-1"


def test_bind_explicit_mime_hint_disqualifies_mismatches() -> None:
    from artifact_handling import bind_produced_artifacts

    schema = {
        "type": "object",
        "properties": {
            "artifact_id": {
                "type": "string",
                "x_artifact_ref": "single",
                "x_artifact_mime": ["image/svg+xml"],
            }
        },
        "required": ["artifact_id"],
    }
    produced = [
        _produced(0, True, "png-1", "render.png", "Rendered image", "image/png"),
        _produced(0, False, "svg-1", "drawing.svg", "Vector drawing", "image/svg+xml"),
    ]

    resolved = bind_produced_artifacts({}, schema, produced)
    assert resolved["artifact_id"] == "svg-1"


def test_bind_overrides_stale_value_but_keeps_chain_produced_value() -> None:
    from artifact_handling import bind_produced_artifacts

    schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "x_artifact_ref": "single"}
        },
        "required": ["artifact_id"],
    }
    produced = [_produced(0, True, "new-1", "output.step", "Revised model", "model/step")]

    # Stale planning-time binding is overridden...
    resolved = bind_produced_artifacts({"artifact_id": "old-1"}, schema, produced)
    assert resolved["artifact_id"] == "new-1"
    # ...but a value already pointing at chain output is preserved.
    resolved = bind_produced_artifacts({"artifact_id": "new-1"}, schema, produced)
    assert resolved["artifact_id"] == "new-1"


def test_bind_falls_back_to_latest_primary_without_descriptions() -> None:
    from artifact_handling import bind_produced_artifacts

    schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "x_artifact_ref": "single"}
        },
        "required": ["artifact_id"],
    }
    produced = [
        _produced(0, True, "a-1", "first.step"),
        _produced(1, True, "b-1", "second.step"),
        _produced(1, False, "b-2", "side.json"),
    ]

    resolved = bind_produced_artifacts({}, schema, produced)
    assert resolved["artifact_id"] == "b-1"
