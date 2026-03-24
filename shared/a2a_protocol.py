"""
A2A Protocol Implementation
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class AgentCapability(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

class AgentCard(BaseModel):
    agent_id: str
    name: str
    description: str
    version: str
    capabilities: List[AgentCapability]
    endpoint: str
    status: str = "active"

class TaskRequest(BaseModel):
    task_id: str
    capability: str
    parameters: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    priority: int = Field(default=5, ge=1, le=10)
    timeout_seconds: Optional[int] = None

class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    completed_at: Optional[datetime] = None

class TaskStatusUpdate(BaseModel):
    task_id: str
    status: TaskStatus
    progress: Optional[float] = Field(None, ge=0.0, le=1.0)
    message: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Goal(BaseModel):
    goal_id: str
    description: str
    subtasks: List[Dict[str, Any]]
    required_capabilities: List[str]
    context: Dict[str, Any]

class AgentRegistration(BaseModel):
    agent_card: AgentCard
    health_check_url: str

class A2AMessage(BaseModel):
    message_id: str
    sender: str
    receiver: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
