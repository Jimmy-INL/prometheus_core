"""Tests for Chainlit upload allowlist configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path


def _accepted_binary_extensions() -> list[str]:
    config_path = Path(__file__).resolve().parents[1] / ".chainlit" / "config.toml"
    config = tomllib.loads(config_path.read_text())
    accept = config["features"]["spontaneous_file_upload"]["accept"]
    return accept["application/octet-stream"]


def test_chainlit_upload_accepts_step_files() -> None:
    binary_extensions = _accepted_binary_extensions()
    assert ".stp" in binary_extensions
    assert ".step" in binary_extensions


def test_chainlit_upload_accepts_mesh_files() -> None:
    """Exodus and STL uploads must be in the allowlist to reach the MeshViewer pipeline."""
    binary_extensions = _accepted_binary_extensions()
    assert ".exo" in binary_extensions
    assert ".e" in binary_extensions
    assert ".stl" in binary_extensions
