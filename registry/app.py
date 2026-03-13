"""
Agent Registry Service using fasta2a
Manages agent discovery and registration for the nuclear analysis system.
"""
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime

app = FastAPI(title="Nuclear A2A Agent Registry", version="1.0.0")

# In-memory registry storage
registered_agents: Dict[str, dict] = {}


class AgentRegistration(BaseModel):
    agent_id: str
    name: str
    description: str
    url: str
    capabilities: List[str]
    version: str = "1.0.0"
    agent_card: Optional[dict] = None  # Full agent card with skills, inputSchemas, etc.


class AgentStatus(BaseModel):
    agent_id: str
    status: str
    last_seen: datetime
    url: str


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "registry", "timestamp": datetime.utcnow().isoformat()}


@app.get("/.well-known/agent.json")
async def get_registry_agent_card():
    """Return the registry's own agent card."""
    return {
        "name": "Nuclear A2A Agent Registry",
        "description": "Central registry service for nuclear analysis agents. Manages agent discovery, registration, and health monitoring.",
        "url": "http://localhost:8000",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False
        },
        "skills": [
            {
                "id": "register_agent",
                "name": "Register Agent",
                "description": "Register a new agent with the registry"
            },
            {
                "id": "list_agents",
                "name": "List Agents",
                "description": "List all registered agents and their capabilities"
            },
            {
                "id": "discover_agent",
                "name": "Discover Agent",
                "description": "Find agents by capability"
            }
        ]
    }


@app.post("/agents/register")
async def register_agent(registration: AgentRegistration):
    """Register a new agent with the registry."""
    registered_agents[registration.agent_id] = {
        "agent_id": registration.agent_id,
        "name": registration.name,
        "description": registration.description,
        "url": registration.url,
        "capabilities": registration.capabilities,
        "version": registration.version,
        "agent_card": registration.agent_card,  # Store full agent card
        "status": "active",
        "registered_at": datetime.utcnow().isoformat(),
        "last_seen": datetime.utcnow().isoformat()
    }
    return {"message": f"Agent {registration.agent_id} registered successfully", "agent": registered_agents[registration.agent_id]}


@app.get("/agents")
async def list_agents():
    """List all registered agents."""
    return {"agents": list(registered_agents.values()), "count": len(registered_agents)}


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get details for a specific agent."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return registered_agents[agent_id]


@app.get("/agents/{agent_id}/card")
async def get_agent_card(agent_id: str):
    """Get the complete agent card for a specific agent."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = registered_agents[agent_id]
    agent_card = agent.get("agent_card")

    if not agent_card:
        raise HTTPException(
            status_code=404,
            detail=f"Agent {agent_id} was registered without a complete agent card"
        )

    return agent_card


@app.get("/agents/by-capability/{capability}")
async def find_agents_by_capability(capability: str):
    """Find agents that have a specific capability."""
    matching_agents = [
        agent for agent in registered_agents.values()
        if capability in agent.get("capabilities", [])
    ]
    return {"capability": capability, "agents": matching_agents, "count": len(matching_agents)}


@app.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Unregister an agent from the registry."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    del registered_agents[agent_id]
    return {"message": f"Agent {agent_id} unregistered successfully"}


@app.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    """Update agent's last seen timestamp."""
    if agent_id not in registered_agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    registered_agents[agent_id]["last_seen"] = datetime.utcnow().isoformat()
    return {"message": "Heartbeat received", "agent_id": agent_id}


@app.get("/capabilities")
async def list_capabilities():
    """List all capabilities across all registered agents.

    Returns a flattened list of all skills from all agents with
    their metadata for dynamic routing and discovery.
    """
    capabilities = []
    for agent in registered_agents.values():
        agent_id = agent["agent_id"]
        agent_url = agent["url"]
        agent_name = agent.get("name", agent_id)
        agent_card = agent.get("agent_card", {})

        for skill in agent_card.get("skills", []):
            capabilities.append({
                "skill_id": skill["id"],
                "skill_name": skill.get("name", skill["id"]),
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_url": agent_url,
                "description": skill.get("description", ""),
                "usage_notes": skill.get("usage_notes"),
                "tags": skill.get("tags", []),
                "input_schema": skill.get("inputSchema", {}),
                "expected_duration_seconds": skill.get("expected_duration_seconds"),
                "requires_approval": skill.get("requires_approval", False),
                "provides": skill.get("provides", []),
                "derivation_rules": skill.get("derivation_rules", []),
            })

    return {"capabilities": capabilities, "count": len(capabilities)}


@app.get("/capabilities/search")
async def search_capabilities(
    tag: Optional[str] = None,
    query: Optional[str] = None
):
    """Search capabilities by tag or text query.

    Args:
        tag: Filter by tag (exact match)
        query: Filter by text in description or name (case-insensitive)

    Returns:
        Matching capabilities
    """
    # Get all capabilities first
    all_caps = (await list_capabilities())["capabilities"]

    results = all_caps

    # Filter by tag if provided
    if tag:
        results = [c for c in results if tag in c.get("tags", [])]

    # Filter by query if provided
    if query:
        query_lower = query.lower()
        results = [
            c for c in results
            if query_lower in c.get("description", "").lower()
            or query_lower in c.get("skill_name", "").lower()
            or query_lower in c.get("skill_id", "").lower()
        ]

    return {"capabilities": results, "count": len(results)}


if __name__ == "__main__":
    port = int(os.getenv("REGISTRY_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
