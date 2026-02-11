"""Pytest configuration for storage client tests."""

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring .env file and database connection"
    )


def pytest_collection_modifyitems(config, items):
    """Mark integration tests automatically."""
    for item in items:
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
