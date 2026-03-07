import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from models.workflow import WorkflowRunRequest
from workflows.wf_alchemy import run_demo_workflow
from workflows.wf_fmea import run_fmea_workflow

router = APIRouter(
    prefix="/api/demo",
    tags=["demo-workflow"],
)


@router.post("/workflow/run")
async def run_workflow(body: WorkflowRunRequest, request: Request):
    """Execute the demo workflow and stream step progress as NDJSON."""

    workflow_id = body.workflow_id or f"wf_{uuid.uuid4()}"

    async def event_stream():
        async for event in run_demo_workflow(
            session_id="",
            workflow_id=workflow_id,
            trigger_message=body.message,
            start_step=body.start_step,
            end_step=body.end_step,
        ):
            yield event.to_json() + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "X-Workflow-Id": workflow_id,
            "X-Session-Id": "",
        },
    )


@router.post("/workflow/fmea")
async def run_fmea_workflow_endpoint(body: WorkflowRunRequest, request: Request):
    """Execute the FMEA workflow and stream step progress as NDJSON."""

    workflow_id = body.workflow_id or f"wf_{uuid.uuid4()}"

    async def event_stream():
        async for event in run_fmea_workflow(
            session_id="",
            workflow_id=workflow_id,
            trigger_message=body.message,
            start_step=body.start_step,
            end_step=body.end_step,
        ):
            yield event.to_json() + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "X-Workflow-Id": workflow_id,
            "X-Session-Id": "",
        },
    )
