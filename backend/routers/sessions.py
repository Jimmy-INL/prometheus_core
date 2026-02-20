from fastapi import APIRouter, Request, HTTPException
from models.state import SessionRecord, MessageRecord, WorkflowStepRecord
from state.base import StateRepository

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"]
)


def _get_repo(request: Request) -> StateRepository:
    """Pull the StateRepository instance from app.state."""
    return request.app.state.repo


@router.get("/{session_id}", response_model=SessionRecord)
async def get_session(session_id: str, request: Request):
    """Get session metadata."""
    repo = _get_repo(request)
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/messages", response_model=list[MessageRecord])
async def get_session_messages(session_id: str, request: Request):
    """Get all messages in a session, in chronological order."""
    repo = _get_repo(request)
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await repo.get_messages(session_id)


@router.get("/{session_id}/workflow-steps", response_model=list[WorkflowStepRecord])
async def get_session_workflow_steps(session_id: str, request: Request):
    """Get all workflow steps in a session."""
    repo = _get_repo(request)
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return await repo.get_workflow_steps(session_id)


@router.get("/user/{user_id}", response_model=list[SessionRecord])
async def list_user_sessions(user_id: str, request: Request):
    """List all sessions for a user, ordered by most recent first."""
    repo = _get_repo(request)
    return await repo.list_sessions(user_id)
