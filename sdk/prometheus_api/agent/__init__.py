"""Agent utilities for building A2A (Agent-to-Agent) multi-agent systems."""

from .worker_pool import UserWorkerPool, WorkerHandle, WorkerTask, WorkerResult
from .ownership import (
    assert_conversation_owner,
    get_conversation_owner,
    list_user_conversations,
    record_conversation_owner,
)
from .identity import (
    IdentityError,
    UserIdentity,
    USER_TOKEN_METADATA_KEY,
    identity_scope,
    get_current_identity,
    current_user_id,
    mint_user_token,
    verify_user_token,
)
from .middleware import BearerTokenMiddleware
from .base import (
    AgentEndpoint,
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
    Part,
)

__all__ = [
    # worker pool
    "UserWorkerPool",
    "WorkerHandle",
    "WorkerTask",
    "WorkerResult",
    # ownership
    "assert_conversation_owner",
    "get_conversation_owner",
    "list_user_conversations",
    "record_conversation_owner",
    # identity
    "IdentityError",
    "UserIdentity",
    "USER_TOKEN_METADATA_KEY",
    "identity_scope",
    "get_current_identity",
    "current_user_id",
    "mint_user_token",
    "verify_user_token",
    # auth
    "BearerTokenMiddleware",
    "AgentEndpoint",
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
    "Part",
]
