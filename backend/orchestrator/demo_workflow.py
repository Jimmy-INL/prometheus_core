"""
Demo workflow: Reactor Primary Coolant System Design.

Defines the workflow steps with canned agent responses and an async generator
that executes them sequentially, yielding NDJSON events for streaming to the
frontend. Each step is recorded in the DB via the existing StateRepository.

Steps can either use a canned response (for demo/testing) or make a real A2A
call to an agent endpoint. Set ``a2a_endpoint`` on a step to enable live mode;
the canned ``response`` is used as a fallback if the A2A call fails.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from state.base import StateRepository
from orchestrator.a2a_client import send_task, A2AError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStepDef:
    name: str
    agent: str
    prompt: str
    delay: float  # seconds to simulate processing
    response: str  # canned response (also used as fallback when A2A fails)
    artifact_url: Optional[str] = None
    a2a_endpoint: Optional[str] = None  # e.g. "http://localhost:8300" — set to enable live A2A
    a2a_timeout: float = 60.0  # per-step A2A timeout in seconds
    a2a_headers: Optional[dict[str, str]] = None  # extra headers (e.g. auth)


DEMO_WORKFLOW_STEPS: list[WorkflowStepDef] = [
    # WorkflowStepDef(
    #     name="planning",
    #     agent="Orchestrator",
    #     prompt="Create plan for: design a reactor primary coolant system",
    #     delay=1.5,
    #     response=(
    #         "Plan created:\n"
    #         "1. Generate requirements for a primary coolant system\n"
    #         "2. Extract functions and system architecture from requirements\n"
    #         "3. Generate 3D model from system architecture"
    #     ),
    # ),
    WorkflowStepDef(
        name="requirements",
        agent="Requirements Agent",
        # prompt="Design a rankine cycle based power generation system with water-based coolant",
        prompt="",
        delay=2.0,
        response=(
            "fallback..."
        ),
        a2a_endpoint="https://api.hpc.inl.gov/llm2/a2a/9a826c6d-5d27-4721-9917-4b5473c934b6",
        a2a_headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-bim-agent-key"
        }
    ),
    # WorkflowStepDef(
    #     name="architecture",
    #     agent="Systems Architecture Agent",
    #     prompt="Extract functions and system architecture from this requirement",
    #     delay=2.5,
    #     response=(
    #         "System Architecture Extracted:\n"
    #         "- System A: Primary Heat Transport Loop\n"
    #         "  - A1: Reactor Coolant Pump (4x, 35,000 GPM each)\n"
    #         "  - A2: Hot Leg Piping (42-inch diameter, Inconel 690)\n"
    #         "  - A3: Cold Leg Piping (42-inch diameter, Inconel 690)\n"
    #         "- System B: Steam Generation\n"
    #         "  - B1: Steam Generator (4x, vertical U-tube)\n"
    #         "  - B2: Pressurizer (2,250 psia, electric heater + spray)"
    #     ),
    # ),
    WorkflowStepDef(
        name="3d_model",
        agent="Alchemy/BIM Agent",
        prompt="Generate a 3D Model for an architecture containing 2 systems and 5 components",
        delay=3.0,
        response="fallback..",
        artifact_url="/demo/ifc",
        a2a_endpoint="https://api.hpc.inl.gov/llm2/a2a/015cf994-9cbc-4116-bba1-a75e72f67dcc",
        a2a_headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-bim-agent-key"
        }
    ),
    # WorkflowStepDef(
    #     name="create_ecar",
    #     agent="ECAR Agent",
    #     prompt="Take the information from this workflow and turn it into an engineering, caculation, and analysis report (ECAR)",
    #     delay=3.0,
    #     response="Here is your ECAR.",
    #     artifact_url="/demo/ecar",
    # ),
]


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

@dataclass
class WorkflowEvent:
    event_type: str  # workflow_start | step_start | step_complete | workflow_complete
    step_index: Optional[int] = None
    step_name: Optional[str] = None
    agent: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    artifact_url: Optional[str] = None
    total_steps: Optional[int] = None
    workflow_id: Optional[str] = None
    timestamp: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if v is not None})


# ---------------------------------------------------------------------------
# Workflow runner (async generator)
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _execute_step(step_def: WorkflowStepDef) -> str:
    """Run a single step — live A2A call if configured, otherwise canned response."""
    if step_def.a2a_endpoint:
        try:
            log.info("A2A call to %s for step '%s'", step_def.a2a_endpoint, step_def.name)
            response = await send_task(
                endpoint=step_def.a2a_endpoint,
                message=step_def.prompt,
                timeout=step_def.a2a_timeout,
                headers=step_def.a2a_headers,
            )
            log.info("A2A response received for step '%s'", step_def.name)
            return response
        except (A2AError, Exception) as exc:
            log.warning(
                "A2A call failed for step '%s': %s — falling back to canned response",
                step_def.name,
                exc,
            )
            return step_def.response
    else:
        # Canned mode: simulate processing time
        await asyncio.sleep(step_def.delay)
        return step_def.response


async def run_demo_workflow(
    session_id: str,
    workflow_id: str,
    trigger_message: str,
    repo: Optional[StateRepository] = None,
) -> AsyncGenerator[WorkflowEvent, None]:
    """Execute the demo workflow and yield events as each step progresses."""

    steps = DEMO_WORKFLOW_STEPS

    yield WorkflowEvent(
        event_type="workflow_start",
        workflow_id=workflow_id,
        total_steps=len(steps),
        timestamp=_now(),
    )

    for i, step_def in enumerate(steps):
        # Record step in DB
        step_record = None
        if repo:
            step_record = await repo.add_workflow_step(
                session_id=session_id,
                workflow_id=workflow_id,
                step_name=step_def.name,
                step_type=step_def.agent,
                input_data={"prompt": step_def.prompt},
            )
            await repo.update_workflow_step(
                step_id=step_record.id,
                status="running",
            )

        yield WorkflowEvent(
            event_type="step_start",
            step_index=i,
            step_name=step_def.name,
            agent=step_def.agent,
            prompt=step_def.prompt,
            total_steps=len(steps),
            timestamp=_now(),
        )

        # Execute the step: live A2A call or canned response
        response_text = await _execute_step(step_def)

        # Record completion in DB
        output_data = {"response": response_text}
        if step_def.artifact_url:
            output_data["artifact_url"] = step_def.artifact_url

        if repo and step_record:
            await repo.update_workflow_step(
                step_id=step_record.id,
                status="completed",
                output_data=output_data,
            )

        yield WorkflowEvent(
            event_type="step_complete",
            step_index=i,
            step_name=step_def.name,
            agent=step_def.agent,
            response=response_text,
            artifact_url=step_def.artifact_url,
            total_steps=len(steps),
            timestamp=_now(),
        )

    yield WorkflowEvent(
        event_type="workflow_complete",
        workflow_id=workflow_id,
        total_steps=len(steps),
        timestamp=_now(),
    )
