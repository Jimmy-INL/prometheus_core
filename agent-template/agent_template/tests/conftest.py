"""Shared fixtures for TEMPLATE_NAME agent tests.

`RequestContext` and `EventQueue` are mocked, so `_execute` can be exercised
directly without an HTTP server, Redis, or the A2A registry. This mirrors the
pattern used by prometheus_api's own test suite.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make agent.py importable when running pytest from the agent directory.
AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from prometheus_api.agent import EventQueue, RequestContext  # noqa: E402


@pytest.fixture
def context() -> MagicMock:
    """A mock A2A request context with a stable conversation/context id."""
    mock = MagicMock(spec=RequestContext)
    mock.context_id = "test-conversation"
    mock.task_id = "test-task"
    return mock


@pytest.fixture
def event_queue() -> AsyncMock:
    """A mock event queue; assert on `enqueue_event` calls to check emissions."""
    return AsyncMock(spec=EventQueue)
