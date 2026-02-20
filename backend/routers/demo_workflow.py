import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from orchestrator.demo_workflow import run_demo_workflow
from state.base import StateRepository

router = APIRouter(
    prefix="/api/demo",
    tags=["demo-workflow"],
)


def _get_repo(request: Request) -> StateRepository:
    return request.app.state.repo


class WorkflowRunRequest(BaseModel):
    message: str
    user_id: str = "user_123"
    session_id: Optional[str] = None


@router.post("/workflow/run")
async def run_workflow(body: WorkflowRunRequest, request: Request):
    """Execute the demo workflow and stream step progress as NDJSON."""
    repo = _get_repo(request)

    # Resolve or create session
    if body.session_id:
        session = await repo.get_session(body.session_id)
        if session is None:
            session = await repo.create_session(body.user_id)
    else:
        session = await repo.create_session(body.user_id)

    workflow_id = f"wf_{uuid.uuid4()}"

    async def event_stream():
        async for event in run_demo_workflow(
            session_id=session.id,
            workflow_id=workflow_id,
            trigger_message=body.message,
            repo=repo,
        ):
            yield event.to_json() + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "X-Workflow-Id": workflow_id,
            "X-Session-Id": session.id,
        },
    )
