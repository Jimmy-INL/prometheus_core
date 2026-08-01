from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

# The frontend <-> client-agent wire contract is owned by prometheus_api;
# re-exported here so orchestrator modules keep importing from .models.
from prometheus_api.contract import (  # noqa: F401
    ConversationRequest,
    ConversationResponse,
    ConversationStatus,
)


class AgentState(TypedDict):
    """State for a conversation's orchestration lifecycle."""
    messages: List[Dict[str, Any]]

    # Conversation tracking
    conversation_id: Optional[str]
    user_query: Optional[str]
    conversation_history: List[Dict]
    prior_capability_params: Dict[str, Dict[str, Any]]

    # Dynamic routing decision
    routing_decision: Optional[Dict[str, Any]]  # Full RoutingDecision.to_dict()

    # Planning phase
    plan: Optional[Dict]
    missing_info: List[str]
    awaiting_approval: bool

    # All pending INPUT_REQUIRED requests from subagents in the current invocation.
    # Each entry has: skill_id, A2A IDs, Task Graph IDs, missing_inputs, and hint.
    pending_subagent_requests: List[Dict[str, Any]]

    # Query parameters (extracted from routing decision)
    material_id: Optional[str]
    analysis_types: Optional[List[str]]
    context: Optional[Dict[str, Any]]
    question: Optional[str]

    # Results
    tool_results: Dict[str, Any]
    final_report: Optional[str]
