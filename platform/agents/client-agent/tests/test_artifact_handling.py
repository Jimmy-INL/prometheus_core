"""Unit tests for artifact catalog helpers."""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from artifact_handling import merge_artifact_catalogs


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
