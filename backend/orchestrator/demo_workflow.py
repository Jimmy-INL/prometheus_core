"""
Demo workflow: Reactor Primary Coolant System Design.

Defines the workflow steps with canned agent responses and an async generator
that executes them sequentially, yielding NDJSON events for streaming to the
frontend. Each step is recorded in the DB via the existing StateRepository.
"""

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from state.base import StateRepository


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStepDef:
    name: str
    agent: str
    prompt: str
    delay: float  # seconds to simulate processing
    response: str
    artifact_url: Optional[str] = None


DEMO_WORKFLOW_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        name="planning",
        agent="Orchestrator",
        prompt="Create plan for: design a reactor primary coolant system",
        delay=1.5,
        response=(
            "Plan created:\n"
            "1. Generate requirements for a primary coolant system\n"
            "2. Extract functions and system architecture from requirements\n"
            "3. Generate 3D model from system architecture"
        ),
    ),
    WorkflowStepDef(
        name="requirements",
        agent="Requirements Agent",
        prompt="Generate requirements for a primary coolant system",
        delay=2.0,
        response=(
            "The primary coolant system shall transfer 300 MWth of heat from "
            "the reactor core to the heat rejection system. The system shall "
            "operate at 2,250 psia with an inlet temperature of 550\u00b0F and "
            "outlet temperature of 620\u00b0F. The system shall maintain a "
            "minimum flow rate of 140,000 GPM during normal operations."
        ),
    ),
    WorkflowStepDef(
        name="architecture",
        agent="Systems Architecture Agent",
        prompt="Extract functions and system architecture from this requirement",
        delay=2.5,
        response=(
            "System Architecture Extracted:\n"
            "- System A: Primary Heat Transport Loop\n"
            "  - A1: Reactor Coolant Pump (4x, 35,000 GPM each)\n"
            "  - A2: Hot Leg Piping (42-inch diameter, Inconel 690)\n"
            "  - A3: Cold Leg Piping (42-inch diameter, Inconel 690)\n"
            "- System B: Steam Generation\n"
            "  - B1: Steam Generator (4x, vertical U-tube)\n"
            "  - B2: Pressurizer (2,250 psia, electric heater + spray)"
        ),
    ),
    WorkflowStepDef(
        name="3d_model",
        agent="Alchemy Agent",
        prompt="Generate a 3D Model for an architecture containing 2 systems and 5 components",
        delay=3.0,
        response="3D model generated: plant.ifc containing 2 systems, 5 components, 847 building elements",
        artifact_url="/demo/ifc",
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

        # Simulate agent processing time
        await asyncio.sleep(step_def.delay)

        # Record completion in DB
        output_data = {"response": step_def.response}
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
            response=step_def.response,
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
