from typing import AsyncGenerator, Optional
from models.workflow import WorkflowStepDef, WorkflowEvent
from orchestrator.utilities import _now, _execute_step


FMEA_Workflow: list[WorkflowStepDef] = [
    WorkflowStepDef(
        name="Prompt_FMEA_Step_1",
        agent="Orchestrator",
        prompt="Describe the main function(s) of {user_input_system}",
        delay=2,
        response=(
            "Step 1 – Define Main Functions:\n"
            "• Clearly describe the overall mission and primary functional objectives of the system.\n"
            "• Capture high-level performance requirements and operational boundaries.\n"
            "• Define what constitutes overall system success."
        ),
    ),

    WorkflowStepDef(
        name="Prompt_FMEA_Step_2",
        agent="Orchestrator",
        prompt="Identify all subfunctions required to accomplish the main function",
        delay=2,
        response=(
            "Step 2 – Identify Subfunctions:\n"
            "• Decompose the main function into all necessary subfunctions.\n"
            "• Include operational, control, monitoring, support, and safety-related subfunctions.\n"
            "• Ensure functional completeness across all operating states."
        ),
    ),

    WorkflowStepDef(
        name="Prompt_FMEA_Step_3",
        agent="SystemsEngineer",
        prompt="For each subfunction, define structural success criteria at Train and Loop/Path levels",
        delay=2,
        response=(
            "Step 3 – Define Structural Success Criteria:\n"
            "For each subfunction:\n"
            "• Define Train-level success (redundant system trains and minimum number required).\n"
            "• Define Loop/Path-level success (physical flow paths and minimum required).\n"
            "• Specify quantitative success thresholds.\n"
            "• Identify credited Recovery Actions.\n"
            "• Identify credited Human Actions at Train or Loop level."
        ),
    ),

    WorkflowStepDef(
        name="Prompt_FMEA_Step_4",
        agent="SystemsEngineer",
        prompt="Identify required Primary and Supporting Systems for each Train or Loop",
        delay=2,
        response=(
            "Step 4 – Identify Required Systems:\n"
            "For each Train or Loop:\n"
            "• Identify Primary Systems required for functional success.\n"
            "• Identify Supporting Systems (power, cooling, control, instrumentation, etc.).\n"
            "• Classify each system as:\n"
            "  - Embedded (dedicated to a specific Train/Loop)\n"
            "  - Shared (used by multiple Trains/Loops; recommend separate modeling).\n"
            "• Document system interdependencies."
        ),
    ),

    WorkflowStepDef(
        name="Prompt_FMEA_Step_5",
        agent="ReliabilityEngineer",
        prompt="List components and evaluate unavailability based on and failure sequence",
        delay=2,
        response=(
            "Step 5 – Component Identification and Impact Assessment:\n"
            "• Provide a complete list of components for each identified system.\n"
            "• Map components to their respective Trains and Loops.\n"
            "• Using {IE_json_block} and the failure sequence:\n"
            "  - Identify failed components.\n"
            "  - Determine which systems become unavailable.\n"
            "  - Determine impacted Trains or Loops.\n"
            "  - Identify loss of redundancy or success criteria violations."
        ),
    ),

    WorkflowStepDef(
        name="Prompt_FMEA_Step_6",
        agent="ReliabilityEngineer",
        prompt="Identify possible failure modes for each component type",
        delay=2,
        response=(
            "Step 6 – Failure Mode Identification:\n"
            "For each component type:\n"
            "• Identify all credible failure modes (mechanical, electrical, control, structural, etc.).\n"
            "• Include failure-to-operate, spurious operation, degradation, and leakage modes.\n"
            "• Consider both internal failures and external/common-cause contributors.\n"
            "• Document functional impact of each failure mode."
        ),
    ),
]



async def run_fmea_workflow(
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

    all_steps = FMEA_Workflow
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
