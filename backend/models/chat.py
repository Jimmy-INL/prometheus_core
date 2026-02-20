from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

# ============================================================================
# Pydantic Models
# ============================================================================

class ChatMessageRequest(BaseModel):
    message: str
    user_id: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = {}
    files: Optional[List[str]] = []

class ResponseType(str, Enum):
    CHAT = "chat"
    WORKFLOW = "workflow"


class ChatResponse(BaseModel):
    type: ResponseType
    session_id: Optional[str] = None
    response: Optional[str] = None
    stream: Optional[bool] = None
    workflow_id: Optional[str] = None
    workflow_type: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    estimated_duration: Optional[str] = None
    polling_url: Optional[str] = None


class WorkflowTriggerRequest(BaseModel):
    workflow_type: str
    user_id: str
    input: Dict[str, Any]


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = None
    modifications: Optional[Dict[str, Any]] = None


class RejectRequest(BaseModel):
    reason: str
    feedback: Optional[str] = None

