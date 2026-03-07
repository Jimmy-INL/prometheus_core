from fastapi import APIRouter

from typing import Dict, Any

router = APIRouter(
    prefix="/api/agents",
    tags=["agents"]
)


@router.get("/")
async def list_agents():
    """
    List all available agents
    """
    pass


@router.post("/{agent_id}/invoke")
async def invoke_agent(agent_id: str, input_data: Dict[str, Any]):
    """
    Directly invoke a specific agent
    """
    pass

