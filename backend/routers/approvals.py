from fastapi import APIRouter

from models.chat import RejectRequest, ApprovalDecisionRequest

router = APIRouter(
    prefix="/approvals",
    tags=["approvals"]
)
# ============================================================================
# Approval Endpoints
# ============================================================================
@router.get("/api/approvals/user/{user_id}")
async def get_user_pending_approvals(user_id: str):
    """
    Get all pending approvals for a user across all workflows
    """
    pass


@router.get("/api/workflows/{workflow_id}/pending-approval")
async def get_workflow_pending_approval(workflow_id: str):
    """
    Get details of pending approval for a specific workflow
    """
    pass


@router.post("/api/workflows/{workflow_id}/approve")
async def approve_workflow_step(
    workflow_id: str,
    request: ApprovalDecisionRequest
):
    """
    Approve a workflow step (optionally with modifications)
    """
    pass


@router.post("/api/workflows/{workflow_id}/reject")
async def reject_workflow_step(
    workflow_id: str,
    request: RejectRequest
):
    """
    Reject a workflow step
    """
    pass


@router.get("/api/workflows/{workflow_id}/steps/{step_number}/preview")
async def get_step_preview(workflow_id: str, step_number: int):
    """
    Get preview data for a step awaiting approval
    """
    pass
