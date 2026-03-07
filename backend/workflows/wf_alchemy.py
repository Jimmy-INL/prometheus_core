from typing import AsyncGenerator, Optional
from models.workflow import WorkflowStepDef, WorkflowEvent
from orchestrator.utilities import _now, _execute_step

DEMO_WORKFLOW_STEPS: list[WorkflowStepDef] = [
    WorkflowStepDef(
        name="planning",
        agent="Orchestrator",
        prompt="Create plan for: Design a Rankine cycle based power generation system for a Sodium Fast Reactor. Core power rating is 390 MW, turbine output is 170.9 MW",
        delay=2,
        response=(
            "Plan created:\n"
            "1. Generate requirements\n"
            "2. Extract functions and system architecture from requirements\n"
            "3. Generate 3D model from system architecture"
        ),
    ),
    WorkflowStepDef(
        name="requirements",
        agent="Requirements Agent",
        # prompt="Design a rankine cycle based power generation system with water-based coolant",
        prompt="",
        delay=5.0,
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
        agent="BIM Agent",
        prompt="Generate a 3D Model for an architecture containing 2 systems and 5 components",
        delay=5.0,
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


async def run_demo_workflow(
    session_id: str,
    workflow_id: str,
    trigger_message: str,
    start_step: int = 0,
    end_step: Optional[int] = None,
) -> AsyncGenerator[WorkflowEvent, None]:
    """Execute the demo workflow and yield events as each step progresses.

    ``start_step`` / ``end_step`` control which slice of
    ``DEMO_WORKFLOW_STEPS`` to run (end_step is exclusive).  The reported
    ``total_steps`` always reflects the full workflow so the frontend can
    show consistent progress numbers.
    """

    all_steps = DEMO_WORKFLOW_STEPS
    total = len(all_steps)
    steps = all_steps[start_step:end_step]

    yield WorkflowEvent(
        event_type="workflow_start",
        workflow_id=workflow_id,
        total_steps=total,
        timestamp=_now(),
    )

    for i, step_def in enumerate(steps, start=start_step):
        # Record step in DB
        step_record = None

        yield WorkflowEvent(
            event_type="step_start",
            step_index=i,
            step_name=step_def.name,
            agent=step_def.agent,
            prompt=step_def.prompt,
            total_steps=total,
            timestamp=_now(),
        )

        # Execute the step: live A2A call or canned response
        response_text = await _execute_step(step_def)

        # Record completion in DB
        output_data = {"response": response_text}
        if step_def.artifact_url:
            output_data["artifact_url"] = step_def.artifact_url

        yield WorkflowEvent(
            event_type="step_complete",
            step_index=i,
            step_name=step_def.name,
            agent=step_def.agent,
            response=response_text,
            artifact_url=step_def.artifact_url,
            total_steps=total,
            timestamp=_now(),
        )

    # Only emit workflow_complete when the run includes the final step
    last_step_ran = start_step + len(steps) - 1 if steps else -1
    if last_step_ran == total - 1:
        yield WorkflowEvent(
            event_type="workflow_complete",
            workflow_id=workflow_id,
            total_steps=total,
            timestamp=_now(),
        )
