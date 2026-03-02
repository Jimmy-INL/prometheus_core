from fastapi import APIRouter, Request, HTTPException
from models.chat import ChatMessageRequest, ChatResponse, ResponseType
from state.base import StateRepository

router = APIRouter(
    prefix="/api",
    tags=["chat"]
)


def _get_repo(request: Request) -> StateRepository:
    """Pull the StateRepository instance from app.state.

    The repo is initialized during the FastAPI lifespan (see main.py)
    and stored on app.state.repo. This helper provides typed access
    so route handlers work against the abstract interface, not the
    concrete SQLite implementation.
    """
    return request.app.state.repo


# ============================================================================
# Chat Endpoints
# ============================================================================
@router.post("/chat", response_model=ChatResponse)
async def chat(request_body: ChatMessageRequest, request: Request):
    """
    Main chat endpoint - routes to direct response or workflow trigger
    """
    repo = _get_repo(request)

    # Resolve or create session
    if request_body.session_id:
        session = await repo.get_session(request_body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = await repo.create_session(request_body.user_id)

    # Store the user's message
    user_metadata = {}
    if request_body.context:
        user_metadata["context"] = request_body.context
    if request_body.files:
        user_metadata["files"] = request_body.files

    await repo.add_message(
        session_id=session.id,
        role="user",
        content=request_body.message,
        metadata=user_metadata or None,
    )

    # Build response
    options = [
        "Design a rankine cycle based power generation system with water-based coolant",
        "Run FTL Safety Analysis"
    ]
    if request_body.message in options:
        # Workflow Triggered response
        response = ChatResponse(
            type="workflow",
            session_id=session.id,
            workflow_id="wf_a7b3c9d2-4e5f-6a1b-8c9d-0e1f2a3b4c5d",
            workflow_type="research_and_report",
            status="queued",
            response=f"You trigger a workflow! Workflow: {request_body.message}",
            estimated_duration="8-12 minutes",
            polling_url="/api/workflows/wf_a7b3c9d2-4e5f-6a1b-8c9d-0e1f2a3b4c5d/status"
        )
    else:
        # Simple chat response
        response = ChatResponse(
            type=ResponseType.CHAT,
            session_id=session.id,
            response=f"This is a basic chat response! From the request we got: {request_body.message}",
            stream=False
        )

    # Store the assistant's response
    await repo.add_message(
        session_id=session.id,
        role="assistant",
        content=response.response or "",
        response_type=response.type.value,
    )

    # If workflow, record the initial step
    if response.type == ResponseType.WORKFLOW and response.workflow_id:
        await repo.add_workflow_step(
            session_id=session.id,
            workflow_id=response.workflow_id,
            step_name="workflow_triggered",
            step_type=response.workflow_type or "unknown",
            input_data={"message": request_body.message},
        )

    return response
