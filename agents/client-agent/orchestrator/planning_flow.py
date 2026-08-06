from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from prometheus_api import load_prompt

from artifact_handling import collect_chain_required_paths
from capability_cache import get_capability_cache
from param_schema import (
    get_nested_value,
    has_param_path,
    is_user_input_schema,
)
from planner import PlanningResult, WorkflowPlanningCandidate, compile_plan_with_tools
from workflow_library import get_workflow_registry, workflow_slug, workflow_tool_name

from . import runtime
from .models import AgentState
from .parameters import (
    build_plan_param_metadata,
    collect_selected_skill_properties,
    filter_missing_params,
    get_selected_skills,
    order_skills_for_workflow,
    resolve_params_via_capability_metadata,
)
from .parameter_extraction import extract_parameters_with_schemas
from .utils import extract_json_from_text, extract_material_ids_from_text

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PLAN_REFINEMENT_PROMPT_TEMPLATE = load_prompt(
    "plan_refinement.txt",
    prompts_dir=PROMPTS_DIR,
)


def _capability_params(
    selected_skills: List[str],
    capabilities_by_skill: Dict[str, Any],
    extracted_params: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Keep the exact prior inputs for each successful capability turn."""
    result: Dict[str, Dict[str, Any]] = {}
    for skill_id in selected_skills:
        capability = capabilities_by_skill.get(skill_id)
        schema = capability.input_schema if capability else {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        values = {
            name: extracted_params[name]
            for name in properties
            if name in extracted_params
        }
        if values:
            result[skill_id] = values
    return result


def _unsupported_message(planning_result: PlanningResult) -> str:
    descriptions_by_id = {
        operation.operation_id: operation.description
        for operation in planning_result.operations
    }
    descriptions = [
        descriptions_by_id.get(item.operation_id, item.operation_id)
        for item in planning_result.unsupported_operations
    ]
    if not descriptions:
        return "I can't complete this request because it contains an unsupported operation."
    if len(descriptions) == 1:
        return (
            "I can't complete this request because no registered capability supports: "
            f"{descriptions[0]}."
        )
    return (
        "I can't complete this request because no registered capabilities support these operations: "
        + "; ".join(descriptions)
        + "."
    )


def _unique_workflow_skills(workflow) -> List[str]:
    skills: List[str] = []
    for step in workflow.definition.steps:
        if step.skill_id and step.skill_id not in skills:
            skills.append(step.skill_id)
    return skills


def _workflow_candidate_from_template(
    workflow,
    *,
    score: float = 0.0,
    selection_source: str = "llm_tool",
    extracted_params: Optional[Dict[str, Any]] = None,
) -> WorkflowPlanningCandidate:
    return WorkflowPlanningCandidate(
        workflow_id=workflow.definition.id,
        workflow_version=workflow.definition.version,
        score=score,
        required_paths=list(workflow.required_input_paths),
        selection_source=selection_source,
        skills=_unique_workflow_skills(workflow),
        execution_mode=workflow.definition.execution.mode,
        estimated_duration_seconds=workflow.definition.metadata.estimated_duration_seconds,
        display_name=workflow.definition.ui.display_name or workflow.definition.name,
        summary=workflow.definition.ui.summary or workflow.definition.description,
        extracted_params=dict(extracted_params or {}),
        tool_name=workflow_tool_name(workflow.definition.id),
    )


def _workflow_named_in_query(query: str, workflows: List[Any]) -> Optional[Any]:
    normalized_query = f"_{workflow_slug(query)}_"
    matches: List[Any] = []
    for workflow in workflows:
        definition = workflow.definition
        labels = {
            str(definition.id or "").strip(),
            str(definition.name or "").strip(),
            str(definition.ui.display_name or "").strip(),
        }
        if any(
            label and f"_{workflow_slug(label)}_" in normalized_query
            for label in labels
        ):
            matches.append(workflow)
    return matches[0] if len(matches) == 1 else None


async def compile_query_plan(
    state: AgentState,
    explicit_workflow_id: Optional[str] = None,
    explicit_workflow_version: Optional[str] = None,
    selection_source: Optional[str] = None,
    seed_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile an execution plan via planner tool calls (no subagent side effects)."""
    query = state.get("user_query", "") or ""
    conversation_history = state.get("conversation_history", [])
    context = state.get("context", {}) or {}
    planning_context = dict(context)
    prior_capability_params = state.get("prior_capability_params")
    if isinstance(prior_capability_params, dict) and prior_capability_params:
        planning_context["prior_capability_params"] = prior_capability_params
    conversation_id = state.get("conversation_id")
    runtime.store_status_update(
        conversation_id,
        "Planning request: loading workflows and selecting capabilities.",
    )

    cache = get_capability_cache()
    capabilities = await cache.get_capabilities()
    capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}
    seed_params = dict(seed_params or {})

    workflow_registry = get_workflow_registry() if runtime.ENABLE_WORKFLOW_LIBRARY else None
    matched_workflow = None
    workflow_candidates: List[WorkflowPlanningCandidate] = []
    if workflow_registry is not None:
        registered_workflows = workflow_registry.list_all()
        workflow_candidates = [
            _workflow_candidate_from_template(workflow)
            for workflow in registered_workflows
        ]
        selected = None
        if explicit_workflow_id:
            selected = workflow_registry.get(explicit_workflow_id, version=explicit_workflow_version)
        else:
            selected = _workflow_named_in_query(query, registered_workflows)
            if selected is not None:
                explicit_workflow_id = selected.definition.id
                explicit_workflow_version = selected.definition.version
                selection_source = "workflow_name"
        if selected:
            matched_workflow = selected
            selected_candidate = _workflow_candidate_from_template(
                selected,
                score=1.0,
                selection_source=selection_source or "catalog",
                extracted_params=seed_params,
            )
            workflow_candidates = [
                selected_candidate,
                *[
                    candidate
                    for candidate in workflow_candidates
                    if not (
                        candidate.workflow_id == selected_candidate.workflow_id
                        and candidate.workflow_version == selected_candidate.workflow_version
                    )
                ],
            ]

    # Explicit workflow selections bypass matcher/router selection and resolve requirements directly.
    if explicit_workflow_id and matched_workflow is not None:
        runtime.store_status_update(
            conversation_id,
            f"Using selected workflow template '{matched_workflow.definition.id}'.",
        )
        selected_skills = _unique_workflow_skills(matched_workflow)
        runtime.store_status_update(
            conversation_id,
            "Extracting parameters with selected capability schemas.",
        )
        extracted_params = await extract_parameters_with_schemas(
            query=query,
            capabilities=[
                capabilities_by_skill[skill_id]
                for skill_id in selected_skills
                if skill_id in capabilities_by_skill
            ],
            history=conversation_history,
            context=planning_context,
            existing_params=seed_params,
        )
        extracted_params = await resolve_params_via_capability_metadata(
            query=query,
            extracted_params=extracted_params,
            selected_skills=selected_skills,
            context=context,
            conversation_history=conversation_history,
        )
        required_params = sorted(set(matched_workflow.required_input_paths))
        requires_approval = bool(matched_workflow.definition.metadata.requires_approval)
        for skill_id in selected_skills:
            cap = capabilities_by_skill.get(skill_id)
            if not cap:
                continue
            if cap.requires_approval:
                requires_approval = True
        missing_required_params = [path for path in required_params if not has_param_path(extracted_params, path)]
        if missing_required_params:
            runtime.store_status_update(
                conversation_id,
                "Missing required parameters: " + ", ".join(missing_required_params),
            )

        merged_context = dict(context)
        if isinstance(extracted_params.get("context"), dict):
            merged_context.update(extracted_params["context"])
        for key, value in extracted_params.items():
            if key.startswith("context.") and value is not None:
                merged_context[key.split(".", 1)[1]] = value
        param_metadata = build_plan_param_metadata(
            selected_skills=selected_skills,
            capabilities_by_skill=capabilities_by_skill,
            selected_workflow=matched_workflow,
        )

        routing_decision = {
            "primary_skill": selected_skills[0] if selected_skills else None,
            "supporting_skills": selected_skills[1:] if len(selected_skills) > 1 else [],
            "workflow_type": "workflow_template",
            "workflow_id": matched_workflow.definition.id,
            "workflow_version": matched_workflow.definition.version,
            "workflow_match_score": 1.0,
            "selection_source": selection_source or "catalog",
            "confidence": 1.0,
            "needs_clarification": False,
            "clarification_question": None,
            "extracted_params": extracted_params,
            "reasoning": f"Selected workflow {matched_workflow.definition.id}",
            "agent_url": None,
            "requires_approval": requires_approval,
            "required_params": required_params,
            "missing_required_params": missing_required_params,
            "capability_params": _capability_params(
                selected_skills,
                capabilities_by_skill,
                extracted_params,
            ),
        }
        plan_steps = [
            f"Step {idx}: Invoke '{step.skill_id}' ({step.id})"
            for idx, step in enumerate(matched_workflow.definition.steps, 1)
        ]
        runtime.store_status_update(
            conversation_id,
            (
                f"Routing decision: templated workflow "
                f"'{matched_workflow.definition.id}@{matched_workflow.definition.version}'."
            ),
        )
        return {
            "is_fallback": False,
            "routing_decision": routing_decision,
            "material_id": extracted_params.get("material_id"),
            "analysis_types": extracted_params.get("analysis_types", []),
            "context": merged_context,
            "question": extracted_params.get("question"),
            "plan": {
                "intent": matched_workflow.definition.description,
                "workflow_type": "workflow_template",
                "workflow_id": matched_workflow.definition.id,
                "workflow_version": matched_workflow.definition.version,
                "skills": selected_skills,
                "required_params": required_params,
                "steps": plan_steps,
                "missing_info": missing_required_params,
                "estimated_duration_seconds": matched_workflow.definition.metadata.estimated_duration_seconds or 120,
                "param_metadata": param_metadata,
            },
            "missing_info": missing_required_params,
            "planner_message": "I've prepared the selected workflow plan. Please review and approve.",
        }

    runtime.store_status_update(conversation_id, "Calling planner LLM for routing decision.")
    planning_result = await compile_plan_with_tools(
        query=query,
        capabilities=capabilities,
        history=conversation_history,
        context=planning_context,
        workflow_candidates=workflow_candidates,
        forced_workflow_id=explicit_workflow_id,
        forced_workflow_version=explicit_workflow_version,
        forced_selection_source=selection_source,
        status_callback=lambda msg: runtime.store_status_update(conversation_id, msg),
    )

    if planning_result.outcome == "unsupported":
        message = _unsupported_message(planning_result)
        runtime.store_status_update(
            conversation_id,
            "Request contains unsupported operations; no capabilities were invoked.",
            final=True,
        )
        return {
            "is_fallback": True,
            "fallback_message": message,
        }

    if planning_result.outcome == "fallback" or (
        not planning_result.primary_skill and not planning_result.workflow_id
    ):
        message = planning_result.message or "I couldn't find a capability plan for that request."
        runtime.store_status_update(conversation_id, "No capability plan found for this request.", final=True)
        return {
            "is_fallback": True,
            "fallback_message": message,
        }

    resolved_query = planning_result.resolved_query or query
    selected_skills: List[str] = [planning_result.primary_skill]
    for skill_id in planning_result.supporting_skills:
        if skill_id and skill_id not in selected_skills:
            selected_skills.append(skill_id)

    selected_workflow = None
    selected_workflow_candidate: Optional[WorkflowPlanningCandidate] = None
    if planning_result.workflow_id and workflow_registry is not None:
        selected_workflow = workflow_registry.get(
            planning_result.workflow_id,
            version=planning_result.workflow_version,
        )
        for candidate in workflow_candidates:
            if candidate.workflow_id != planning_result.workflow_id:
                continue
            if planning_result.workflow_version and candidate.workflow_version != planning_result.workflow_version:
                continue
            selected_workflow_candidate = candidate
            break
        if selected_workflow:
            wf_skills = _unique_workflow_skills(selected_workflow)
            if wf_skills:
                selected_skills = wf_skills

    primary_capability = capabilities_by_skill.get(planning_result.primary_skill)
    if primary_capability is None and selected_skills:
        primary_capability = capabilities_by_skill.get(selected_skills[0])
    if primary_capability is None and selected_workflow is None:
        runtime.store_status_update(
            conversation_id,
            f"Selected capability '{planning_result.primary_skill}' is unavailable.",
            final=True,
        )
        return {
            "is_fallback": True,
            "fallback_message": (
                f"Capability '{planning_result.primary_skill}' is currently unavailable. "
                "Please retry after discovery refresh."
            ),
        }

    required_params_set = set(selected_workflow.required_input_paths if selected_workflow else [])
    runtime_required_params_set: set[str] = set()
    requires_approval = False
    if selected_workflow and selected_workflow.definition.metadata.requires_approval:
        requires_approval = True
    chain_capabilities = [capabilities_by_skill.get(skill_id) for skill_id in selected_skills]
    if selected_workflow is None:
        # Sequential artifact-reference inputs of downstream skills are
        # runtime-produced — deferring them here keeps the approved plan from
        # immediately bouncing back as INPUT_REQUIRED.
        chain = collect_chain_required_paths(chain_capabilities, planning_result.workflow_type)
        required_params_set.update(chain.user_paths)
        runtime_required_params_set.update(chain.runtime_paths)
    if any(cap and cap.requires_approval for cap in chain_capabilities):
        requires_approval = True

    required_params = sorted(required_params_set)
    runtime_required_params = sorted(runtime_required_params_set)
    extracted_seed = dict(seed_params)
    if selected_workflow_candidate and selected_workflow_candidate.extracted_params:
        extracted_seed.update(selected_workflow_candidate.extracted_params)
    extracted_seed.update(planning_result.extracted_params)
    runtime.store_status_update(
        conversation_id,
        "Extracting parameters with selected capability schemas.",
    )
    extracted_params = await extract_parameters_with_schemas(
        query=resolved_query,
        capabilities=[
            capability
            for capability in chain_capabilities
            if capability is not None
        ],
        history=conversation_history,
        context=planning_context,
        existing_params=extracted_seed,
    )
    extracted_params = await resolve_params_via_capability_metadata(
        query=resolved_query,
        extracted_params=extracted_params,
        selected_skills=selected_skills,
        context=context,
        conversation_history=conversation_history,
    )
    unresolved_runtime_params = [
        path for path in runtime_required_params
        if not has_param_path(extracted_params, path)
    ]
    if selected_workflow is None and unresolved_runtime_params:
        runtime.store_status_update(
            conversation_id,
            (
                "Planner selected capabilities with unresolved runtime inputs: "
                + ", ".join(unresolved_runtime_params)
            ),
            final=True,
        )
        return {
            "is_fallback": True,
            "fallback_message": (
                "I couldn't execute that plan directly because it requires internal runtime inputs. "
                "Please request a workflow plan that includes upstream specialist steps."
            ),
        }

    missing_required_params = [
        path for path in required_params
        if not has_param_path(extracted_params, path)
    ]
    if missing_required_params:
        runtime.store_status_update(
            conversation_id,
            "Missing required parameters: " + ", ".join(missing_required_params),
        )

    merged_context = dict(context)
    if isinstance(extracted_params.get("context"), dict):
        merged_context.update(extracted_params["context"])
    for key, value in extracted_params.items():
        if key.startswith("context.") and value is not None:
            merged_context[key.split(".", 1)[1]] = value

    material_id = extracted_params.get("material_id")
    analysis_types = extracted_params.get("analysis_types", [])
    if isinstance(analysis_types, str):
        analysis_types = [analysis_types]

    steps = planning_result.steps
    if not steps:
        if selected_workflow is not None:
            for idx, step in enumerate(selected_workflow.definition.steps, 1):
                steps.append(f"Step {idx}: Invoke '{step.skill_id}' ({step.id})")
        else:
            for idx, skill_id in enumerate(selected_skills, 1):
                cap = capabilities_by_skill.get(skill_id)
                skill_name = cap.skill_name if cap else skill_id
                skill_desc = cap.description if cap else "Invoke capability"
                steps.append(f"Step {idx}: Invoke '{skill_name}' ({skill_id}) - {skill_desc}")

    estimated_duration = planning_result.estimated_duration_seconds
    if not estimated_duration or estimated_duration < 1:
        estimated_duration = 0
        for skill_id in selected_skills:
            cap = capabilities_by_skill.get(skill_id)
            estimated_duration += cap.expected_duration_seconds if cap and cap.expected_duration_seconds else 30

    routing_decision = {
        "primary_skill": planning_result.primary_skill or (selected_skills[0] if selected_skills else None),
        "supporting_skills": [skill for skill in selected_skills[1:]] if selected_skills else [],
        "workflow_type": planning_result.workflow_type,
        "workflow_id": planning_result.workflow_id,
        "workflow_version": planning_result.workflow_version,
        "workflow_match_score": planning_result.workflow_match_score,
        "selection_source": planning_result.selection_source,
        "confidence": planning_result.confidence,
        "needs_clarification": False,
        "clarification_question": None,
        "extracted_params": extracted_params,
        "reasoning": planning_result.reasoning or planning_result.message or resolved_query,
        "agent_url": primary_capability.agent_url if primary_capability else None,
        "requires_approval": requires_approval,
        "required_params": required_params,
        "missing_required_params": missing_required_params,
        "operations": [
            operation.model_dump()
            for operation in planning_result.operations
        ],
        "operation_coverage": dict(planning_result.operation_coverage),
    }
    if planning_result.resolution_kind:
        routing_decision["turn_resolution"] = {
            "kind": planning_result.resolution_kind,
            "standalone_request": resolved_query,
            "referenced_invocation_id": planning_result.referenced_invocation_id,
        }
    if selected_workflow is not None:
        routing_decision["capability_params"] = _capability_params(
            selected_skills,
            capabilities_by_skill,
            extracted_params,
        )
    if planning_result.workflow_type == "workflow_template" and planning_result.workflow_id:
        runtime.store_status_update(
            conversation_id,
            (
                f"Routing decision: templated workflow "
                f"'{planning_result.workflow_id}@{planning_result.workflow_version}'."
            ),
        )
    elif planning_result.workflow_type == "single":
        runtime.store_status_update(
            conversation_id,
            f"Routing decision: single capability '{routing_decision.get('primary_skill')}'.",
        )
    else:
        skill_list = ", ".join(selected_skills) if selected_skills else "(none)"
        runtime.store_status_update(
            conversation_id,
            f"Routing decision: {planning_result.workflow_type} multi-skill plan ({skill_list}).",
        )
    param_metadata = build_plan_param_metadata(
        selected_skills=selected_skills,
        capabilities_by_skill=capabilities_by_skill,
        selected_workflow=selected_workflow,
    )

    return {
        "is_fallback": False,
        "routing_decision": routing_decision,
        "material_id": material_id,
        "analysis_types": analysis_types,
        "context": merged_context,
        "question": extracted_params.get("question"),
        "plan": {
            "intent": planning_result.reasoning or planning_result.message or resolved_query,
            "workflow_type": planning_result.workflow_type,
            "workflow_id": planning_result.workflow_id,
            "workflow_version": planning_result.workflow_version,
            "skills": selected_skills,
            "required_params": required_params,
            "steps": steps,
            "missing_info": missing_required_params,
            "estimated_duration_seconds": estimated_duration,
            "param_metadata": param_metadata,
            "operations": [
                operation.model_dump()
                for operation in planning_result.operations
            ],
        },
        "missing_info": missing_required_params,
        "planner_message": planning_result.message,
    }


async def extract_refinement_param_updates(
    query: str,
    routing_decision: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract parameter updates from plan-refinement instructions.

    Unlike follow-up extraction, refinement extraction considers both required and
    optional user-facing fields so users can tweak assumptions without reopening
    missing-info flow.
    """
    text = str(query or "").strip()
    if not text or not isinstance(routing_decision, dict):
        return {}

    selected_skills = get_selected_skills(routing_decision)
    properties = await collect_selected_skill_properties(selected_skills)

    candidate_paths: List[str] = []
    workflow_type = routing_decision.get("workflow_type")
    workflow_id = routing_decision.get("workflow_id")
    workflow_version = routing_decision.get("workflow_version")
    if workflow_type == "workflow_template" and workflow_id and runtime.ENABLE_WORKFLOW_LIBRARY:
        workflow = get_workflow_registry().get(str(workflow_id), version=workflow_version)
        if workflow:
            candidate_paths.extend(list(workflow.required_input_paths))
            candidate_paths.extend(list(workflow.definition.inputs.optional or []))

    if not candidate_paths:
        for path, prop in properties.items():
            if not isinstance(prop, dict):
                continue
            is_object = prop.get("type") == "object" or "properties" in prop
            if is_object:
                continue
            if is_user_input_schema(prop):
                candidate_paths.append(path)
    else:
        filtered: List[str] = []
        for path in candidate_paths:
            prop = properties.get(path)
            if not prop and "." in path:
                prop = properties.get(path.split(".", 1)[1], {})
            if isinstance(prop, dict) and not is_user_input_schema(prop):
                continue
            filtered.append(path)
        candidate_paths = filtered

    normalized_paths: List[str] = []
    seen_paths = set()
    for path in candidate_paths:
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        normalized_paths.append(path)
    if not normalized_paths:
        return {}

    param_schema = {}
    for path in normalized_paths:
        prop = properties.get(path)
        if not prop and "." in path:
            prop = properties.get(path.split(".", 1)[1], {})
        param_schema[path] = prop if isinstance(prop, dict) and prop else {"type": "string"}

    history_lines: List[str] = []
    for item in (conversation_history or [])[-8:]:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "").strip()
        if content:
            history_lines.append(f"{role}: {content}")
    history_block = "\n".join(history_lines) if history_lines else "(none)"

    current_params = routing_decision.get("extracted_params", {}) or {}
    prompt = PLAN_REFINEMENT_PROMPT_TEMPLATE.format(
        text=text,
        history_block=history_block,
        current_params_json=json.dumps(current_params, indent=2, default=str),
        normalized_paths_json=json.dumps(normalized_paths, indent=2),
        param_schema_json=json.dumps(param_schema, indent=2, default=str),
    )

    async with runtime.create_llm() as llm:
        response = await llm.medium(prompt, temperature=0, max_tokens=4096)
    parsed = extract_json_from_text(response.text)
    if not isinstance(parsed, dict):
        return {}

    updates: Dict[str, Any] = {}
    for path in normalized_paths:
        value = get_nested_value(parsed, path)
        if value is None and path in parsed:
            value = parsed.get(path)
        if value is None or value == "":
            continue
        if path == "material_id":
            inferred = extract_material_ids_from_text(str(value))
            if inferred:
                updates["material_id"] = inferred[0]
                updates["material_ids"] = inferred
                continue
        updates[path] = value

    return updates


def plan_analysis(state: AgentState) -> Dict:
    """Create a capability-driven execution plan with no hardcoded agent logic.

    Generates an execution plan dynamically from capability metadata. The plan includes:
    - Intent/reasoning from routing decision
    - Ordered list of skills to invoke
    - Step-by-step description of what will happen
    - Estimated duration from capability metadata
    - Missing parameters that need to be provided

    All plan details come from agent card metadata - there is no hardcoded knowledge
    of what specific skills do.

    Args:
        state: Current workflow state with routing_decision

    Returns:
        State updates with generated plan
    """
    routing_decision = state.get("routing_decision", {}) or {}
    existing_plan = state.get("plan")
    if isinstance(existing_plan, dict) and existing_plan.get("steps"):
        provided_params = routing_decision.get("extracted_params", {}) or {}
        required_params = existing_plan.get("required_params") or routing_decision.get("required_params", []) or []
        missing = filter_missing_params(
            required_params,
            provided_params,
            fallback_missing=(
                routing_decision.get("missing_required_params", []) or state.get("missing_info", [])
            ),
        )

        preserved_plan = dict(existing_plan)
        preserved_plan["missing_info"] = missing
        if "workflow_type" not in preserved_plan:
            preserved_plan["workflow_type"] = routing_decision.get("workflow_type", "single")
        if "skills" not in preserved_plan:
            preserved_plan["skills"] = order_skills_for_workflow(routing_decision)
        return {
            "plan": preserved_plan,
            "missing_info": missing,
            "messages": [],
        }

    selected_skills = order_skills_for_workflow(routing_decision)
    provided_params = routing_decision.get("extracted_params", {}) or {}
    required_params = routing_decision.get("required_params", []) or []
    missing = filter_missing_params(
        required_params,
        provided_params,
        fallback_missing=(
            routing_decision.get("missing_required_params", []) or state.get("missing_info", [])
        ),
    )

    # Build plan steps from capability metadata
    capability_cache = get_capability_cache()
    steps: List[str] = []
    estimated_duration = 0

    for idx, skill_id in enumerate(selected_skills, 1):
        capability = capability_cache.get_by_skill_id(skill_id)
        skill_name = capability.skill_name if capability else skill_id
        skill_desc = capability.description if capability else "Invoke capability"
        steps.append(f"Step {idx}: Invoke '{skill_name}' ({skill_id}) - {skill_desc}")
        estimated_duration += capability.expected_duration_seconds if capability and capability.expected_duration_seconds else 30

    if not steps:
        steps = ["Invoke selected capability based on query intent"]
        estimated_duration = 30

    plan = {
        "intent": routing_decision.get("reasoning") or state.get("user_query") or "Capability execution",
        "workflow_type": routing_decision.get("workflow_type", "single"),
        "skills": selected_skills,
        "required_params": required_params,
        "steps": steps,
        "missing_info": missing,
        "estimated_duration_seconds": estimated_duration,
    }

    return {
        "plan": plan,
        "missing_info": missing,
        "messages": []
    }


def show_plan(state: AgentState) -> Dict:
    """Show plan to user and wait for approval."""
    return {
        "awaiting_approval": True
    }
