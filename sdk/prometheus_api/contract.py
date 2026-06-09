"""Canonical wire contract between the Prometheus frontend and the client-agent.

The Chainlit frontend and the client-agent orchestrator exchange a JSON
payload (``ConversationRequest`` / ``ConversationResponse``) embedded in the
text part of A2A ``message/stream`` calls. These models are the single source
of truth for that payload; both sides must import them from here instead of
maintaining local copies.

Intentionally dependency-light and at the package top level: importing
``prometheus_api.contract`` requires only pydantic, so consumers like the
Chainlit frontend can use it without pulling in the agent runtime
(a2a-sdk, starlette, litellm). The models are also re-exported from
``prometheus_api.agent`` for agent-side convenience.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ConversationStatus(str, Enum):
    """Authoritative set of ``ConversationResponse.status`` values.

    String-valued so existing ``response.status == "completed"`` comparisons
    keep working on both sides of the wire.
    """

    NEEDS_INFO = "needs_info"  # follow-up questions for the user
    PLAN_READY = "plan_ready"  # plan awaiting user approval
    EXECUTING = "executing"  # plan execution in progress
    COMPLETED = "completed"  # multi-step plan finished, report ready
    RECOMMENDATION = "recommendation"  # direct recommendation answer
    ANSWER = "answer"  # direct single-agent answer
    BACKGROUNDED = "backgrounded"  # turn detached to a background task
    ERROR = "error"  # request failed

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]


class ConversationRequest(BaseModel):
    """Frontend → client-agent payload (text part of an A2A message)."""

    model_config = ConfigDict(extra="ignore")

    query: Optional[str] = ""  # Natural language query (optional for followup/approval)
    conversation_id: Optional[str] = None  # For multi-turn
    followup_answers: Optional[Dict] = None  # Answers to followup questions
    plan_approved: Optional[bool] = False  # Approval to execute plan
    plan_rejected: Optional[bool] = False  # Explicit rejection of a pending plan
    artifacts: Optional[List[Dict[str, Any]]] = (
        None  # Conversation artifact references (metadata only)
    )
    workflow_id: Optional[str] = None  # Explicit workflow template selection
    workflow_version: Optional[str] = None  # Optional explicit workflow version
    selection_source: Optional[str] = None  # catalog|matcher|dynamic_router
    uploaded_files: Optional[List[Dict[str, Any]]] = (
        None  # Raw files attached by the user this turn
    )
    newly_uploaded_artifact_ids: Optional[List[str]] = (
        None  # Set by _execute after upload; transient
    )
    received_files: Optional[List[Dict[str, Any]]] = (
        None  # Uploaded files received but not stored this turn
    )


class ConversationResponse(BaseModel):
    """Client-agent → frontend payload (text part of the final status event)."""

    # use_enum_values: status is validated against ConversationStatus but
    # stored/serialized as the plain string, so json.dumps(model_dump()) and
    # `response.status == "completed"` behave identically on both sides.
    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    conversation_id: str = ""
    status: ConversationStatus = ConversationStatus.ANSWER
    message: Optional[str] = None

    # When status == NEEDS_INFO
    followup_questions: Optional[List[Dict]] = None

    # When status == PLAN_READY
    plan: Optional[Dict] = None

    # When status == COMPLETED
    report: Optional[str] = None
    tool_results: Optional[Dict] = None

    # When status == RECOMMENDATION or ANSWER
    response_text: Optional[str] = None
    recommended_materials: Optional[List[str]] = None

    artifacts: Optional[List[Dict[str, Any]]] = None  # full conversation catalog
    new_artifacts: Optional[List[Dict[str, Any]]] = None  # only produced this turn
    message_metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_payload(cls, data: Dict[str, Any]) -> "ConversationResponse":
        """Parse a response payload dict, tolerating unknown extra fields."""
        return cls.model_validate(data)
