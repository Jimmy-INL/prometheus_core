"""Tests for environment-based configuration."""

import os
import pytest
from pathlib import Path
from storage_client import ConnectionConfig


def test_from_env_with_manual_params(monkeypatch):
    """Test from_env with manually provided parameters."""
    # Set env vars
    monkeypatch.setenv("DEEPLYNX_KEY", "test-key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "test-secret")

    # Provide org/project manually
    config = ConnectionConfig.from_env(
        organization_id=123,
        project_id=456
    )

    assert config.organization_id == 123
    assert config.project_id == 456
    assert config.api_key == "test-key"
    assert config.api_secret == "test-secret"
    assert config.uses_api_key is True


def test_from_env_all_from_environment(monkeypatch):
    """Test from_env with all values from environment."""
    monkeypatch.setenv("DEEPLYNX_KEY", "env-key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "env-secret")
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "789")
    monkeypatch.setenv("DEEPLYNX_PROJECT_ID", "101")
    monkeypatch.setenv("DEEPLYNX_BASE_URL", "https://custom.api.com/v1")

    config = ConnectionConfig.from_env()

    assert config.organization_id == 789
    assert config.project_id == 101
    assert config.api_key == "env-key"
    assert config.api_secret == "env-secret"
    assert config.base_url == "https://custom.api.com/v1"


def test_from_env_jwt_token(monkeypatch):
    """Test from_env with JWT token."""
    monkeypatch.setenv("DEEPLYNX_JWT_TOKEN", "test-token")
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "123")
    monkeypatch.setenv("DEEPLYNX_PROJECT_ID", "456")

    config = ConnectionConfig.from_env()

    assert config.jwt_token == "test-token"
    assert config.uses_jwt is True
    assert config.uses_api_key is False


def test_from_env_missing_org_id(monkeypatch):
    """Test from_env fails when org_id is missing."""
    monkeypatch.setenv("DEEPLYNX_KEY", "key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "secret")
    monkeypatch.setenv("DEEPLYNX_PROJECT_ID", "456")

    with pytest.raises(ValueError, match="organization_id must be provided"):
        ConnectionConfig.from_env()


def test_from_env_missing_project_id(monkeypatch):
    """Test from_env fails when project_id is missing."""
    monkeypatch.setenv("DEEPLYNX_KEY", "key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "secret")
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "123")

    with pytest.raises(ValueError, match="project_id must be provided"):
        ConnectionConfig.from_env()


def test_from_env_parameter_override(monkeypatch):
    """Test that manual parameters override environment variables."""
    monkeypatch.setenv("DEEPLYNX_KEY", "env-key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "env-secret")
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "100")

    # Override with manual param
    config = ConnectionConfig.from_env(
        organization_id=999,
        project_id=888
    )

    assert config.organization_id == 999  # Manual override
    assert config.project_id == 888       # Manual override
    assert config.api_key == "env-key"    # From env


def test_from_env_custom_kwargs(monkeypatch):
    """Test from_env with custom ConnectionConfig kwargs."""
    monkeypatch.setenv("DEEPLYNX_KEY", "key")
    monkeypatch.setenv("DEEPLYNX_SECRET", "secret")
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "123")
    monkeypatch.setenv("DEEPLYNX_PROJECT_ID", "456")

    config = ConnectionConfig.from_env(
        timeout=60.0,
        max_retries=5,
        verify_ssl=False
    )

    assert config.timeout == 60.0
    assert config.max_retries == 5
    assert config.verify_ssl is False


def test_from_env_no_credentials(monkeypatch):
    """Test from_env fails when no credentials are provided."""
    monkeypatch.setenv("DEEPLYNX_ORG_ID", "123")
    monkeypatch.setenv("DEEPLYNX_PROJECT_ID", "456")

    with pytest.raises(ValueError, match="Must provide either jwt_token"):
        ConnectionConfig.from_env()


def test_from_env_env_file_precedence(tmp_path, monkeypatch):
    """Test that .env file is loaded when specified."""
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("""
DEEPLYNX_KEY=file-key
DEEPLYNX_SECRET=file-secret
DEEPLYNX_ORG_ID=999
DEEPLYNX_PROJECT_ID=888
""")

    # Make sure environment doesn't have these
    monkeypatch.delenv("DEEPLYNX_KEY", raising=False)
    monkeypatch.delenv("DEEPLYNX_SECRET", raising=False)

    # Load from file
    config = ConnectionConfig.from_env(env_file=env_file)

    assert config.organization_id == 999
    assert config.project_id == 888
    assert config.api_key == "file-key"
    assert config.api_secret == "file-secret"
