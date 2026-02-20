from abc import ABC, abstractmethod
from typing import Optional

from models.state import SessionRecord, MessageRecord, WorkflowStepRecord


class StateRepository(ABC):
    """Abstract interface for session state persistence.

    Implementations must provide all methods. The interface is designed
    so the storage backend can be swapped without changing router code.
    """

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    # -- Sessions --

    @abstractmethod
    async def create_session(self, user_id: str) -> SessionRecord:
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[SessionRecord]:
        ...

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[SessionRecord]:
        ...

    # -- Messages --

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        response_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MessageRecord:
        ...

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[MessageRecord]:
        ...

    # -- Workflow Steps --

    @abstractmethod
    async def add_workflow_step(
        self,
        session_id: str,
        workflow_id: str,
        step_name: str,
        step_type: str,
        input_data: Optional[dict] = None,
    ) -> WorkflowStepRecord:
        ...

    @abstractmethod
    async def update_workflow_step(
        self,
        step_id: str,
        status: str,
        output_data: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> Optional[WorkflowStepRecord]:
        ...

    @abstractmethod
    async def get_workflow_steps(self, session_id: str) -> list[WorkflowStepRecord]:
        ...
