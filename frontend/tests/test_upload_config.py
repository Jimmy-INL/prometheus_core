"""Tests for Chainlit upload allowlist configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_chainlit_upload_accepts_step_files() -> None:
    config_path = Path(__file__).resolve().parents[1] / ".chainlit" / "config.toml"
    config = tomllib.loads(config_path.read_text())
    accept = config["features"]["spontaneous_file_upload"]["accept"]
    binary_extensions = accept["application/octet-stream"]

    assert ".stp" in binary_extensions
    assert ".step" in binary_extensions
