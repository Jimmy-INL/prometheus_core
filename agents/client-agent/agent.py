"""Client Agent - orchestrates specialist agents for nuclear engineering requests.

The implementation lives under ``orchestrator/``; this module is the Docker
entry point.
"""
from orchestrator import runtime
from orchestrator.service import OrchestratorAgent

__all__ = ["OrchestratorAgent"]


if __name__ == "__main__":
    agent = OrchestratorAgent()
    agent.run(port=runtime.AGENT_PORT)
