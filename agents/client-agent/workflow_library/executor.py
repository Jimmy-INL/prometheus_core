"""Workflow executor with sequential/parallel/dag scheduling semantics."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from .binding import get_path, resolve_step_params, set_path
from .schema import CompiledWorkflow, WorkflowStep


StepInvokeFn = Callable[[str, Dict[str, Any], str], Awaitable[Dict[str, Any]]]


@dataclass
class StepRuntimeResult:
    step_id: str
    status: str
    result: Any = None
    error: str | None = None
    input_required: Dict[str, Any] | None = None


def _ordered_steps(workflow: CompiledWorkflow) -> List[WorkflowStep]:
    return list(workflow.definition.steps)


def _dependencies_succeeded(step: WorkflowStep, statuses: Dict[str, str]) -> bool:
    for dep in step.depends_on:
        if statuses.get(dep) != "succeeded":
            return False
    return True


def _dependency_failed_or_blocked(step: WorkflowStep, statuses: Dict[str, str]) -> bool:
    for dep in step.depends_on:
        dep_status = statuses.get(dep)
        if dep_status in {"failed", "blocked"}:
            return True
    return False


def _should_skip_by_when(step: WorkflowStep, context: Dict[str, Any]) -> bool:
    when = step.when or {}
    not_in_context = when.get("not_in_context")
    if isinstance(not_in_context, str):
        return get_path(context, not_in_context) is not None
    return False


async def _run_step(
    step: WorkflowStep,
    workflow: CompiledWorkflow,
    input_params: Dict[str, Any],
    context: Dict[str, Any],
    step_results: Dict[str, Any],
    invoke_skill: StepInvokeFn,
    conversation_id: str,
) -> StepRuntimeResult:
    payload = resolve_step_params(
        params_spec=step.params,
        input_params=input_params,
        context=context,
        step_results=step_results,
    )
    payload["conversation_id"] = conversation_id

    invoked = await invoke_skill(step.skill_id, payload, conversation_id)
    if "input_required" in invoked:
        return StepRuntimeResult(
            step_id=step.id,
            status="input_required",
            input_required=invoked.get("input_required"),
        )
    if "error" in invoked:
        return StepRuntimeResult(
            step_id=step.id,
            status="failed",
            error=str(invoked.get("error")),
        )
    return StepRuntimeResult(
        step_id=step.id,
        status="succeeded",
        result=invoked.get("result"),
    )


def _apply_step_outputs(
    step: WorkflowStep,
    result: Any,
    context: Dict[str, Any],
    context_delta: Dict[str, Any],
) -> None:
    for output in step.outputs or []:
        if not isinstance(output, dict):
            continue
        to_context = output.get("to_context")
        from_path = output.get("from")
        if not to_context:
            continue
        if from_path:
            value = get_path(result, str(from_path))
            if value is None and str(from_path) == "result":
                value = result
        else:
            value = result
        if value is None:
            continue
        set_path(context, str(to_context), value)
        set_path(context_delta, str(to_context), value)


def _resolve_final_output(workflow: CompiledWorkflow, step_results: Dict[str, Any]) -> Any:
    final_ref = (workflow.definition.outputs.final or {}).get("from")
    if isinstance(final_ref, str) and final_ref:
        source = {"step": step_results}
        if final_ref.startswith("step."):
            return get_path(source, final_ref)
        return get_path(step_results, final_ref)

    for step in workflow.definition.steps:
        if step.is_final and step.id in step_results:
            return step_results[step.id].get("result")
    if workflow.definition.steps:
        last_id = workflow.definition.steps[-1].id
        if last_id in step_results:
            return step_results[last_id].get("result")
    return None


async def execute_workflow(
    workflow: CompiledWorkflow,
    input_params: Dict[str, Any],
    context: Dict[str, Any],
    invoke_skill: StepInvokeFn,
    conversation_id: str,
) -> Dict[str, Any]:
    """Execute a compiled workflow with dependency-aware scheduling."""
    steps = _ordered_steps(workflow)
    step_map = {step.id: step for step in steps}
    statuses: Dict[str, str] = {step.id: "pending" for step in steps}
    results: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []
    input_required_steps: List[Dict[str, Any]] = []
    context_delta: Dict[str, Any] = {}

    mode = workflow.definition.execution.mode
    max_concurrency = max(1, int(workflow.definition.execution.max_concurrency or 1))
    on_error = workflow.definition.execution.on_error

    stop_scheduling = False
    while True:
        pending = [step_id for step_id, status in statuses.items() if status == "pending"]
        if not pending:
            break

        ready_steps: List[WorkflowStep] = []
        for step_id in pending:
            step = step_map[step_id]
            if _dependency_failed_or_blocked(step, statuses):
                statuses[step_id] = "blocked"
                continue
            if not _dependencies_succeeded(step, statuses):
                continue
            if _should_skip_by_when(step, context):
                statuses[step_id] = "skipped"
                continue
            ready_steps.append(step)

        if stop_scheduling or not ready_steps:
            # If no steps can run, convert remaining pending to blocked.
            for step_id in pending:
                if statuses[step_id] == "pending":
                    statuses[step_id] = "blocked"
            break

        if mode == "sequential":
            ready_steps = [ready_steps[0]]
        elif mode == "parallel":
            # Run currently ready set together (bounded by max_concurrency).
            ready_steps = ready_steps[:max_concurrency]
        else:  # dag
            ready_steps = ready_steps[:max_concurrency]

        for step in ready_steps:
            statuses[step.id] = "running"

        tasks = [
            _run_step(
                step=step,
                workflow=workflow,
                input_params=input_params,
                context=context,
                step_results=results,
                invoke_skill=invoke_skill,
                conversation_id=conversation_id,
            )
            for step in ready_steps
        ]
        done = await asyncio.gather(*tasks, return_exceptions=False)

        for item in done:
            step = step_map[item.step_id]
            statuses[item.step_id] = item.status
            if item.status == "succeeded":
                results[item.step_id] = {
                    "skill_id": step.skill_id,
                    "result": item.result,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
                _apply_step_outputs(step, item.result, context, context_delta)
            elif item.status == "input_required":
                input_required_steps.append(
                    {
                        "step_id": item.step_id,
                        "skill_id": step.skill_id,
                        "input_required": item.input_required,
                    }
                )
                stop_scheduling = True
            else:
                errors.append(
                    {
                        "step_id": item.step_id,
                        "skill_id": step.skill_id,
                        "error": item.error or "unknown error",
                    }
                )
                if on_error == "fail_fast":
                    stop_scheduling = True

    success = not any(status == "failed" for status in statuses.values())
    final_output = _resolve_final_output(workflow, results)

    return {
        "workflow_id": workflow.definition.id,
        "workflow_version": workflow.definition.version,
        "step_statuses": statuses,
        "step_results": results,
        "errors": errors,
        "input_required_steps": input_required_steps,
        "final_output": final_output,
        "context_delta": context_delta,
        "success": success,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
