"""Agent utilities for building A2A (Agent-to-Agent) multi-agent systems."""

from .middleware import BearerTokenMiddleware
from .base import PrometheusAgent, PrometheusAgentExecutor
from .artifacts import ArtifactReference, ArtifactRegistry

# Re-export commonly used A2A types for convenience
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Artifact,
    TextPart,
)

__all__ = [
    "BearerTokenMiddleware",
    "PrometheusAgent",
    "PrometheusAgentExecutor",
    "ArtifactReference",
    "ArtifactRegistry",
    # A2A types
    "RequestContext",
    "EventQueue",
    "TaskState",
    "TaskStatus",
    "TaskStatusUpdateEvent",
    "TaskArtifactUpdateEvent",
    "Artifact",
    "TextPart",
]
