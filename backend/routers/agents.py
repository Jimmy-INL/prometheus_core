from fastapi import APIRouter

from typing import Dict, Any

router = APIRouter(
    prefix="/agents",
    tags=["agents"]
)

# ============================================================================
# Agent Endpoints (Optional - if you want direct agent access)
# ============================================================================
@router.get("/api/agents")
async def list_agents():
    """
    List all available agents
    """
    pass


@router.post("/api/agents/{agent_id}/invoke")
async def invoke_agent(agent_id: str, input_data: Dict[str, Any]):
    """
    Directly invoke a specific agent
    """
    pass

