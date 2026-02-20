from pydantic import BaseModel
from typing import Optional, Any


class SessionRecord(BaseModel):
    id: str
    user_id: str
    created_at: str
    updated_at: str


class MessageRecord(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    response_type: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: str


class WorkflowStepRecord(BaseModel):
    id: str
    session_id: str
    workflow_id: Optional[str] = None
    step_name: str
    step_type: str
    status: str
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str
