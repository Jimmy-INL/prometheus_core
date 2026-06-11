"""Agent utilities for building A2A (Agent-to-Agent) multi-agent systems."""

from .middleware import BearerTokenMiddleware
from .base import (
    DelegatingPrometheusAgentExecutor,
    MissingInput,
    PrometheusAgent,
    PrometheusAgentExecutor,
)
from .artifact_resolver import ArtifactResolver
from .artifacts import ArtifactReference, ArtifactRegistry
from .context_state import ContextStateStore
from ..contract import ConversationRequest, ConversationResponse, ConversationStatus
from .task_store import RedisTaskStore
from .registry import AgentRegistryClient
from .worker import PrometheusWorker

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
    "DelegatingPrometheusAgentExecutor",
    "MissingInput",
    "PrometheusAgent",
    "PrometheusAgentExecutor",
    "PrometheusWorker",
    "ArtifactReference",
    "ArtifactRegistry",
    "ArtifactResolver",
    "AgentRegistryClient",
    "ContextStateStore",
    "ConversationRequest",
    "ConversationResponse",
    "ConversationStatus",
    "RedisTaskStore",
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
