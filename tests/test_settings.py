"""Tests for utils/settings.py — read_config function."""

from pathlib import Path

import pytest

from utils.settings import read_config


def test_read_config_valid_yaml(sample_config_yaml: Path):
    """Loads a valid YAML file and returns a dict."""
    data = read_config(str(sample_config_yaml))
    assert data["chat-intro"] == "Welcome"
    assert data["chat-suggestion-title"] == "Try these"
    assert data["workflow-suggestions"] == ["Run MOOSE", "Run Alchemy"]


def test_read_config_file_not_found():
    """Raises FileNotFoundError when file doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        read_config("/nonexistent/path/config.yml")


def test_read_config_invalid_yaml(tmp_path: Path):
    """Raises RuntimeError for malformed YAML."""
    bad = tmp_path / "bad.yml"
    bad.write_text("key: [unterminated")
    with pytest.raises(RuntimeError, match="Invalid YAML"):
        read_config(str(bad))


def test_read_config_empty_file(tmp_path: Path):
    """Empty YAML file returns empty dict."""
    empty = tmp_path / "empty.yml"
    empty.write_text("")
    result = read_config(str(empty))
    assert result == {}
