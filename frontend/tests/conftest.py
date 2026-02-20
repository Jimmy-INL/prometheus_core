"""Shared fixtures for frontend tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a small temp file for hash/cache tests."""
    f = tmp_path / "sample.txt"
    f.write_text("hello world")
    return f


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal config.yml for settings tests."""
    config = tmp_path / "config.yml"
    config.write_text(
        "chat-intro: Welcome\nchat-suggestion-title: Try these\nworkflow-suggestions:\n  - Run MOOSE\n  - Run Alchemy\n"
    )
    return config
