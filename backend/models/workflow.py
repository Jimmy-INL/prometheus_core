from typing import Optional
from dataclasses import dataclass, asdict
import json
from pydantic import BaseModel


class WorkflowRunRequest(BaseModel):
    message: str
    user_id: str = "user_123"
    session_id: Optional[str] = None
    workflow_id: Optional[str] = None
    start_step: int = 0
    end_step: Optional[int] = None


@dataclass
class WorkflowStepDef:
    name: str
    agent: str
    prompt: str
    delay: float  # seconds to simulate processing
    response: str  # canned response (also used as fallback when A2A fails)
    artifact_url: Optional[str] = None
    a2a_endpoint: Optional[str] = None  # e.g. "http://localhost:8300" — set to enable live A2A
    a2a_timeout: float = 60.0  # per-step A2A timeout in seconds
    a2a_headers: Optional[dict[str, str]] = None  # extra headers (e.g. auth)


@dataclass
class WorkflowEvent:
    event_type: str  # workflow_start | step_start | step_complete | workflow_complete
    step_index: Optional[int] = None
    step_name: Optional[str] = None
    agent: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    artifact_url: Optional[str] = None
    total_steps: Optional[int] = None
    workflow_id: Optional[str] = None
    timestamp: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if v is not None})
