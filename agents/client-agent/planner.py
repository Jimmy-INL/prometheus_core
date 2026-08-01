"""
LLM tool-calling planner for control-plane routing decisions.

`compile_plan_with_tools` is the single entry point. It is called by `chat()`
in `agent.py` whenever a new query needs to be routed. It drives an LLM
through a structured tool-call loop and returns a `PlanningResult` describing
what to do next — no subagents are invoked here.

HOW IT WORKS
------------
1. A schema-bound LLM call decomposes the request without seeing capabilities.
2. A `_PlanDraft` freezes those operations and accumulates routing state.
3. The routing LLM is given:
   - The user query and conversation history
   - Available capabilities (skills + their input schemas)
   - Optional workflow templates (pre-built execution blueprints)
4. The LLM calls planning tools until it calls `finalize_plan`, at which point
   the loop exits.
5. The `_PlanDraft` is converted to an immutable `PlanningResult` and returned.
6. Parameter extraction runs separately after the planner selects capabilities.

PLANNING TOOLS (called by the LLM, not external code)
------------------------------------------------------
- `select_capabilities`      — choose primary + supporting skills and workflow type
- `workflow_*`              — choose a registered workflow blueprint directly
- `select_workflow_template` — choose a pre-built workflow blueprint by id/version
- `get_workflow_candidates`  — inspect registered workflow options
- `get_requirement_status`   — check which required params are still missing
- `set_plan_steps`           — set human-readable steps shown in the approval UI
- `set_user_message`         — set the planning summary shown to the user
- `set_operation_coverage`   — map every requested operation or mark it unsupported
- `finalize_plan`            — commit the plan (preserves missing user inputs for collection)

OUTCOMES (`PlanningResult.outcome`)
------------------------------------
- `"agent_plan"`  — one or more skills selected; `agent.py` will collect missing
                    params then call `execute_current_plan`
- `"fallback"`    — capability-neutral decomposition produced a conversational
                    response or clarification; `agent.py` returns it directly
- `"unsupported"` — one or more requested operations have no registered
                    capability; no partial plan is executed

WORKFLOW TEMPLATES vs DYNAMIC SKILL SELECTION
---------------------------------------------
Dynamic selection (always available): the planner picks skills freely from the
capability registry. Flexible but requires the agent cards to have good metadata.

Workflow templates (when ENABLE_WORKFLOW_LIBRARY=true): pre-authored blueprints
stored in `workflow_library/`. Registered workflows are exposed to the planner
as dedicated `workflow_*` tools. The planner can call one of those tools, or
select one by id/version via `select_workflow_template`. Templates define fixed
skill sequences, input bindings, and execution order.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from artifact_handling import collect_chain_required_paths
from capability_cache import AgentCapability
from file_upload_handler import mime_type_label
from param_schema import (
    extract_required_param_paths,
    flatten_schema_properties,
    get_nested_value,
    has_param_path,
    set_nested_value,
)
from workflow_library.naming import workflow_tool_name
from orchestrator import runtime

PROMPTS_DIR = Path(__file__).with_name("prompts")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = _load_prompt("planner_system.txt")


class PlanningContractError(RuntimeError):
    """Raised when an LLM planning response violates its declared schema."""


class DecomposedOperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)


class DecomposeRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_kind: Literal["task", "conversation", "needs_clarification"]
    operations: List[DecomposedOperationInput] = Field(default_factory=list)
    message: str = ""


class AssignDependenciesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dependencies: Dict[str, List[str]]


class RequestedOperation(BaseModel):
    """Immutable operation from capability-neutral request decomposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str
    description: str
    depends_on: List[str] = Field(default_factory=list)


class RequestDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_kind: Literal["task", "conversation", "needs_clarification"]
    operations: List[RequestedOperation] = Field(default_factory=list)
    message: str = ""


class CoveredOperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    skill_id: str


class UnsupportedOperationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    reason: str = Field(min_length=1)


class SetOperationCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    covered: List[CoveredOperationInput] = Field(default_factory=list)
    unsupported: List[UnsupportedOperationInput] = Field(default_factory=list)


class SelectCapabilitiesInput(BaseModel):
    primary_skill: str = Field(description="Primary skill id to execute")
    supporting_skills: List[str] = Field(
        default_factory=list,
        description="Optional supporting skill ids",
    )
    workflow_type: Literal["single", "parallel", "sequential"] = Field(
        default="single",
        description="Execution workflow semantics",
    )
    reasoning: str = Field(
        default="",
        description="Short explanation for why these skills are selected",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Planner confidence in the skill selection",
    )


class SelectWorkflowTemplateInput(BaseModel):
    workflow_id: str = Field(description="Workflow template id")
    workflow_version: Optional[str] = Field(default=None, description="Specific version (optional)")
    reasoning: str = Field(default="", description="Short rationale for selecting this workflow")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SelectRegisteredWorkflowInput(BaseModel):
    reasoning: str = Field(default="", description="Short rationale for selecting this workflow")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class SetPlanStepsInput(BaseModel):
    steps: List[str] = Field(
        default_factory=list,
        description="Human-readable plan steps for UI confirmation",
    )
    estimated_duration_seconds: int = Field(
        default=120,
        ge=1,
        description="Estimated end-to-end duration in seconds",
    )


class SetUserMessageInput(BaseModel):
    message: str = Field(
        default="",
        description="Message to show to the user with the generated plan",
    )


class PlanningResult(BaseModel):
    """Structured planner output consumed by `agent.py` chat flow."""

    outcome: Literal["agent_plan", "fallback", "unsupported"] = "agent_plan"
    message: str = ""
    workflow_id: Optional[str] = None
    workflow_version: Optional[str] = None
    workflow_match_score: Optional[float] = None
    selection_source: Optional[str] = None
    primary_skill: Optional[str] = None
    supporting_skills: List[str] = Field(default_factory=list)
    workflow_type: Literal["single", "parallel", "sequential", "workflow_template"] = "single"
    confidence: float = 0.5
    reasoning: str = ""
    extracted_params: Dict[str, Any] = Field(default_factory=dict)
    steps: List[str] = Field(default_factory=list)
    estimated_duration_seconds: int = 120
    operations: List[RequestedOperation] = Field(default_factory=list)
    operation_coverage: Dict[str, str] = Field(default_factory=dict)
    unsupported_operations: List[UnsupportedOperationInput] = Field(default_factory=list)


@dataclass
class _PlanDraft:
    """Mutable draft updated via planning tools during a single planning session."""

    outcome: Literal["agent_plan", "fallback", "unsupported"] = "agent_plan"
    message: str = ""
    workflow_id: Optional[str] = None
    workflow_version: Optional[str] = None
    workflow_match_score: Optional[float] = None
    selection_source: Optional[str] = None
    primary_skill: Optional[str] = None
    supporting_skills: List[str] = field(default_factory=list)
    workflow_type: Literal["single", "parallel", "sequential", "workflow_template"] = "single"
    confidence: float = 0.5
    reasoning: str = ""
    extracted_params: Dict[str, Any] = field(default_factory=dict)
    steps: List[str] = field(default_factory=list)
    estimated_duration_seconds: int = 120
    operations: List[RequestedOperation] = field(default_factory=list)
    covered_operations: Dict[str, str] = field(default_factory=dict)
    unsupported_operations: Dict[str, str] = field(default_factory=dict)
    finalized: bool = False

    def to_result(self) -> PlanningResult:
        return PlanningResult(
            outcome=self.outcome,
            message=self.message,
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            workflow_match_score=self.workflow_match_score,
            selection_source=self.selection_source,
            primary_skill=self.primary_skill,
            supporting_skills=list(self.supporting_skills),
            workflow_type=self.workflow_type,
            confidence=self.confidence,
            reasoning=self.reasoning,
            extracted_params=dict(self.extracted_params),
            steps=list(self.steps),
            estimated_duration_seconds=self.estimated_duration_seconds,
            operations=list(self.operations),
            operation_coverage=dict(self.covered_operations),
            unsupported_operations=[
                UnsupportedOperationInput(operation_id=operation_id, reason=reason)
                for operation_id, reason in self.unsupported_operations.items()
            ],
        )


@dataclass
class WorkflowPlanningCandidate:
    """Workflow candidate exposed to planner tools."""

    workflow_id: str
    workflow_version: str
    score: float
    required_paths: List[str] = field(default_factory=list)
    selection_source: str = "matcher"
    skills: List[str] = field(default_factory=list)
    execution_mode: str = "sequential"
    estimated_duration_seconds: Optional[int] = None
    display_name: Optional[str] = None
    summary: Optional[str] = None
    extracted_params: Dict[str, Any] = field(default_factory=dict)
    tool_name: Optional[str] = None


async def decompose_request(
    *,
    query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> RequestDecomposition:
    """Decompose a request before exposing any registered capabilities."""
    if status_callback:
        status_callback("Planner LLM decomposing the request into operations.")

    messages = [
        {
            "role": "system",
            "content": (
                "Classify and decompose the user's request without considering what tools or "
                "capabilities may be available. Call decompose_request exactly once and return "
                "no prose. For a task, list every requested outcome as an ordered operation. "
                "Do not assign dependencies; those are requested separately after the ordered "
                "operations are frozen. "
                "Treat requests to change previously created parameterized geometry as a new "
                "geometry-authoring outcome followed by any requested downstream outcomes; do "
                "not assume an in-place CAD editing operation. For conversation, return the "
                "direct response in message. For genuinely ambiguous intent, return one focused "
                "question in message."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Current user query:\n{query}\n\n"
                f"Conversation history:\n{json.dumps(history or [], default=str)}\n\n"
                f"Conversation context:\n{json.dumps(context or {}, default=str)}"
            ),
        },
    ]
    tool_schema = {
        "type": "function",
        "function": {
            "name": "decompose_request",
            "description": "Return the exact capability-neutral request decomposition.",
            "parameters": DecomposeRequestInput.model_json_schema(),
        },
    }

    async with runtime.create_llm() as llm:
        response = await llm.medium(
            messages,
            temperature=0,
            max_tokens=2048,
            tools=[tool_schema],
        )

    _, calls = _planning_tool_calls(response.raw)
    if len(calls) != 1 or calls[0].get("name") != "decompose_request":
        raise PlanningContractError(
            "Request decomposition must call decompose_request exactly once."
        )
    try:
        parsed = DecomposeRequestInput.model_validate(calls[0].get("args"))
    except ValidationError as exc:
        raise PlanningContractError(
            f"Request decomposition violates its schema: {exc}"
        ) from exc

    message = parsed.message.strip()
    if parsed.request_kind == "task":
        if not parsed.operations:
            raise PlanningContractError(
                "Task decomposition must contain at least one operation."
            )
        if message:
            raise PlanningContractError(
                "Task decomposition must not include a conversational message."
            )
    else:
        if parsed.operations:
            raise PlanningContractError(
                "Non-task decomposition must not contain operations."
            )
        if not message:
            raise PlanningContractError(
                "Non-task decomposition must include a response or clarification message."
            )

    operation_descriptions: List[str] = []
    for index, operation in enumerate(parsed.operations, 1):
        description = operation.description.strip()
        if not description:
            raise PlanningContractError(
                f"Decomposed operation {index} has an empty description."
            )
        operation_descriptions.append(description)

    dependency_map = {
        f"op_{index}": []
        for index in range(1, len(operation_descriptions) + 1)
    }
    if len(operation_descriptions) > 1:
        if status_callback:
            status_callback("Planner LLM assigning operation dependencies.")
        operation_ids = list(dependency_map)
        dependency_properties = {}
        for index, operation_id in enumerate(operation_ids):
            earlier_ids = operation_ids[:index]
            dependency_properties[operation_id] = {
                "type": "array",
                "description": (
                    f"Earlier operations that {operation_id} directly depends on."
                ),
                "items": (
                    {"type": "string", "enum": earlier_ids}
                    if earlier_ids
                    else {"type": "string"}
                ),
                "uniqueItems": True,
                "maxItems": len(earlier_ids),
            }
        dependency_tool = {
            "type": "function",
            "function": {
                "name": "assign_dependencies",
                "description": (
                    "Assign dependencies among the frozen ordered operations."
                ),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "dependencies": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": dependency_properties,
                            "required": operation_ids,
                        }
                    },
                    "required": ["dependencies"],
                },
            },
        }
        frozen_operations = [
            {"operation_id": operation_id, "description": description}
            for operation_id, description in zip(
                operation_ids, operation_descriptions
            )
        ]
        dependency_messages = [
            {
                "role": "system",
                "content": (
                    "Assign dependencies among the frozen operations. Call "
                    "assign_dependencies exactly once and return no prose. Every operation "
                    "must be present. Dependencies may reference only operation IDs allowed "
                    "by the tool schema. Prior conversation state and artifacts are context, "
                    "not operations in this request."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Current user query:\n{query}\n\n"
                    "Frozen ordered operations:\n"
                    f"{json.dumps(frozen_operations)}"
                ),
            },
        ]
        async with runtime.create_llm() as llm:
            dependency_response = await llm.medium(
                dependency_messages,
                temperature=0,
                max_tokens=1024,
                tools=[dependency_tool],
            )
        _, dependency_calls = _planning_tool_calls(dependency_response.raw)
        if (
            len(dependency_calls) != 1
            or dependency_calls[0].get("name") != "assign_dependencies"
        ):
            raise PlanningContractError(
                "Dependency assignment must call assign_dependencies exactly once."
            )
        try:
            assigned = AssignDependenciesInput.model_validate(
                dependency_calls[0].get("args")
            )
        except ValidationError as exc:
            raise PlanningContractError(
                f"Dependency assignment violates its schema: {exc}"
            ) from exc
        if set(assigned.dependencies) != set(operation_ids):
            raise PlanningContractError(
                "Dependency assignment must contain exactly the frozen operation IDs."
            )
        dependency_map = assigned.dependencies

    operations: List[RequestedOperation] = []
    for index, description in enumerate(operation_descriptions, 1):
        operation_id = f"op_{index}"
        dependencies = dependency_map[operation_id]
        if len(set(dependencies)) != len(dependencies):
            raise PlanningContractError(
                f"Decomposed operation {index} has duplicate dependencies."
            )
        earlier_ids = {f"op_{earlier}" for earlier in range(1, index)}
        invalid_dependencies = [
            dependency
            for dependency in dependencies
            if dependency not in earlier_ids
        ]
        if invalid_dependencies:
            raise PlanningContractError(
                f"Decomposed operation {index} references non-earlier dependencies: "
                + ", ".join(str(item) for item in invalid_dependencies)
            )
        operations.append(
            RequestedOperation(
                operation_id=operation_id,
                description=description,
                depends_on=list(dependencies),
            )
        )

    return RequestDecomposition(
        request_kind=parsed.request_kind,
        operations=operations,
        message=message,
    )


def _set_param_path(params: Dict[str, Any], path: str, value: Any) -> None:
    set_nested_value(params, path, value)


def _get_param_path(params: Dict[str, Any], path: str) -> Any:
    return get_nested_value(params, path)


def _build_capability_context(capabilities: List[AgentCapability]) -> str:
    """Format capability metadata for planner prompt grounding."""
    blocks: List[str] = []
    for cap in capabilities:
        lines = [
            f"- skill_id: {cap.skill_id}",
            f"  agent: {cap.agent_name}",
            f"  description: {cap.description}",
            f"  requires_approval: {cap.requires_approval}",
        ]
        if cap.usage_notes:
            lines.append(f"  usage_notes: {cap.usage_notes}")
        if cap.tags:
            lines.append(f"  tags: {', '.join(cap.tags)}")
        if cap.input_schema:
            required = extract_required_param_paths(cap.input_schema)
            internal_required = sorted(
                set(extract_required_param_paths(cap.input_schema, include_internal=True)) - set(required)
            )
            props = cap.input_schema.get("properties", {}) or {}
            if required:
                lines.append(f"  required_params: {', '.join(required)}")
            if internal_required:
                lines.append(
                    "  internal_required_params: "
                    + ", ".join(internal_required)
                    + " (provided by workflow/runtime, not user)"
                )
            if props:
                prop_lines = []
                for name, info in props.items():
                    desc = str(info.get("description", "")).strip()
                    typ = str(info.get("type", "string"))
                    prop_lines.append(f"{name}({typ}){': ' + desc if desc else ''}")
                if prop_lines:
                    lines.append(f"  params: {', '.join(prop_lines)}")
        if cap.expected_duration_seconds:
            lines.append(f"  expected_duration_seconds: {cap.expected_duration_seconds}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_prompt(
    query: str,
    history: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
    capabilities: List[AgentCapability],
    operations: List[RequestedOperation],
    workflow_candidates: Optional[List[WorkflowPlanningCandidate]] = None,
) -> str:
    """Build planner prompt with full conversation + context + capability metadata."""
    history_lines: List[str] = []
    for item in history:
        role = str(item.get("role", "user"))
        text = str(item.get("content", "")).strip()
        if text:
            history_lines.append(f"{role}: {text}")
        tool_results = item.get("tool_results")
        if isinstance(tool_results, dict) and tool_results:
            history_lines.append(f"{role}_tool_results: {json.dumps(tool_results, default=str)}")

    artifacts_block = ""
    artifacts = (context or {}).get("artifacts")
    newly_uploaded_ids = set((context or {}).get("newly_uploaded_artifact_ids") or [])
    if isinstance(artifacts, list) and artifacts:
        rows = []
        for artifact in artifacts[:12]:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("artifact_id") or "").strip()
            name = str(artifact.get("name") or "").strip()
            desc = str(artifact.get("description") or "").strip()
            if not artifact_id or not name:
                continue
            if artifact_id in newly_uploaded_ids:
                mime = str(artifact.get("mime_type") or "")
                label = mime_type_label(mime, name)
                desc = f"[User-uploaded {label} for this request] {desc}".strip()
            rows.append(f"- {name} (id: {artifact_id}) {desc[:200]}")
        if rows:
            artifacts_block = "Available artifacts:\n" + "\n".join(rows)

    # Files received this turn but not stored (storage unavailable or upload failed).
    received_files = (context or {}).get("received_files") or []
    if received_files:
        received_rows = []
        for f in received_files:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "file")
            mime = str(f.get("mime_type") or "")
            label = mime_type_label(mime, name)
            received_rows.append(f"- {name} ({label}) [received this request — not stored, storage unavailable]")
        if received_rows:
            received_block = "Files received (not stored — storage unavailable):\n" + "\n".join(received_rows)
            artifacts_block = (artifacts_block + "\n" + received_block).strip() if artifacts_block else received_block

    history_block = "\n".join(history_lines) if history_lines else "(none)"
    capability_block = _build_capability_context(capabilities)
    context_block = json.dumps(context or {}, indent=2, default=str)
    operations_block = json.dumps(
        [operation.model_dump() for operation in operations],
        indent=2,
    )
    workflow_block = ""
    if workflow_candidates:
        rows = []
        for candidate in workflow_candidates:
            label = candidate.display_name or candidate.workflow_id
            tool_name = candidate.tool_name or workflow_tool_name(candidate.workflow_id)
            rows.append(
                f"- tool: {tool_name} "
                f"label={label} "
                f"workflow={candidate.workflow_id}@{candidate.workflow_version} "
                f"mode={candidate.execution_mode} "
                f"skills={candidate.skills} "
                f"required={candidate.required_paths}"
            )
        workflow_block = "Registered workflow tools:\n" + "\n".join(rows) + "\n\n"

    return (
        f"User query:\n{query}\n\n"
        f"Full conversation history:\n{history_block}\n\n"
        f"Current conversation context:\n{context_block}\n\n"
        f"Required operations (immutable):\n{operations_block}\n\n"
        f"{workflow_block}"
        f"{artifacts_block}\n\n"
        f"Available capabilities:\n{capability_block}\n"
    ).strip()


def _build_planning_tools(
    draft: _PlanDraft,
    capabilities_by_skill: Dict[str, AgentCapability],
    context: Optional[Dict[str, Any]],
    workflow_candidates: Optional[List[WorkflowPlanningCandidate]] = None,
) -> List[StructuredTool]:
    """Create side-effect-free planning tools for one planning session."""
    planning_context = dict(context or {})
    candidate_list = list(workflow_candidates or [])
    candidates_by_id: Dict[str, List[WorkflowPlanningCandidate]] = {}
    for candidate in candidate_list:
        candidates_by_id.setdefault(candidate.workflow_id, []).append(candidate)
    for workflow_id, items in candidates_by_id.items():
        items.sort(key=lambda item: item.workflow_version, reverse=True)

    def get_selected_workflow_candidate() -> Optional[WorkflowPlanningCandidate]:
        if not draft.workflow_id:
            return None
        options = candidates_by_id.get(draft.workflow_id, [])
        if not options:
            return None
        if draft.workflow_version:
            for candidate in options:
                if candidate.workflow_version == draft.workflow_version:
                    return candidate
        return options[0]

    def selected_skill_ids() -> List[str]:
        if not draft.primary_skill:
            return []
        selected = [draft.primary_skill]
        for skill_id in draft.supporting_skills:
            if skill_id and skill_id not in selected:
                selected.append(skill_id)
        return selected

    def hydrate_context_assumptions(required_paths: List[str]) -> None:
        for path in required_paths:
            if not path.startswith("context.") or has_param_path(draft.extracted_params, path):
                continue
            context_key = path.split(".", 1)[1]
            value = _get_param_path(planning_context, context_key)
            if value is not None:
                _set_param_path(draft.extracted_params, path, value)

    def get_requirement_status() -> Dict[str, Any]:
        selected = selected_skill_ids()
        selected_workflow = get_selected_workflow_candidate()
        if not selected and not selected_workflow:
            return {
                "ok": False,
                "error": (
                    "No skills/workflow selected yet. Call select_capabilities or select_workflow_template first."
                ),
            }

        required_paths_set = set()
        runtime_required_paths_set = set()
        deferred_runtime_paths_set = set()
        properties: Dict[str, Dict[str, Any]] = {}
        if selected_workflow:
            required_paths_set.update(selected_workflow.required_paths)
            # For workflow templates, required inputs come from workflow bindings
            # (`input.*` refs) rather than full downstream skill schemas.
            for skill_id in selected:
                cap = capabilities_by_skill.get(skill_id)
                if cap:
                    properties.update(flatten_schema_properties(cap.input_schema))
        else:
            chain_capabilities = [capabilities_by_skill.get(skill_id) for skill_id in selected]
            chain = collect_chain_required_paths(chain_capabilities, draft.workflow_type)
            required_paths_set.update(chain.user_paths)
            runtime_required_paths_set.update(chain.runtime_paths)
            deferred_runtime_paths_set.update(chain.deferred_paths)
            for cap in chain_capabilities:
                if cap:
                    properties.update(flatten_schema_properties(cap.input_schema))

        required_paths = sorted(required_paths_set)
        runtime_required_paths = sorted(runtime_required_paths_set)
        hydrate_context_assumptions(required_paths)
        missing_paths = [path for path in required_paths if not has_param_path(draft.extracted_params, path)]
        unresolved_runtime_paths = [
            path for path in runtime_required_paths if not has_param_path(draft.extracted_params, path)
        ]

        details: List[Dict[str, Any]] = []
        for path in required_paths:
            prop = properties.get(path)
            if not prop and "." in path:
                prop = properties.get(path.split(".", 1)[1])
            details.append(
                {
                    "path": path,
                    "type": (prop or {}).get("type", "string"),
                    "description": (prop or {}).get("description", ""),
                }
            )

        return {
            "ok": True,
            "required_paths": required_paths,
            "missing_paths": missing_paths,
            "runtime_required_paths": runtime_required_paths,
            "unresolved_runtime_paths": unresolved_runtime_paths,
            # Filled at runtime from earlier sequential steps' outputs; do not
            # ask the user for these and do not treat them as blocking.
            "deferred_runtime_paths": sorted(deferred_runtime_paths_set),
            "details": details,
            "params": draft.extracted_params,
        }

    def get_workflow_candidates() -> Dict[str, Any]:
        payload = [
            {
                "workflow_id": candidate.workflow_id,
                "workflow_version": candidate.workflow_version,
                "tool_name": candidate.tool_name or workflow_tool_name(candidate.workflow_id),
                "required_paths": candidate.required_paths,
                "skills": candidate.skills,
                "execution_mode": candidate.execution_mode,
                "display_name": candidate.display_name,
                "summary": candidate.summary,
                "extracted_params": candidate.extracted_params,
            }
            for candidate in candidate_list
        ]
        return {"ok": True, "candidates": payload}

    def select_workflow_template(
        workflow_id: str,
        workflow_version: Optional[str] = None,
        reasoning: str = "",
        confidence: float = 0.5,
    ) -> Dict[str, Any]:
        options = candidates_by_id.get(workflow_id, [])
        if not options:
            return {"ok": False, "error": f"Unknown workflow_id '{workflow_id}'"}
        selected_candidate = None
        if workflow_version:
            for candidate in options:
                if candidate.workflow_version == workflow_version:
                    selected_candidate = candidate
                    break
            if selected_candidate is None:
                return {
                    "ok": False,
                    "error": f"Unknown workflow version '{workflow_version}' for workflow '{workflow_id}'",
                }
        else:
            selected_candidate = options[0]

        selected_candidate = selected_candidate or options[0]
        draft.workflow_id = selected_candidate.workflow_id
        draft.workflow_version = selected_candidate.workflow_version
        draft.workflow_match_score = float(selected_candidate.score)
        draft.selection_source = selected_candidate.selection_source
        draft.workflow_type = "workflow_template"
        draft.reasoning = (reasoning or draft.reasoning or "").strip()
        draft.confidence = max(0.0, min(1.0, float(confidence)))
        draft.primary_skill = selected_candidate.skills[0] if selected_candidate.skills else None
        draft.supporting_skills = selected_candidate.skills[1:] if len(selected_candidate.skills) > 1 else []
        if selected_candidate.estimated_duration_seconds and selected_candidate.estimated_duration_seconds > 0:
            draft.estimated_duration_seconds = int(selected_candidate.estimated_duration_seconds)
        if selected_candidate.extracted_params:
            merged = dict(selected_candidate.extracted_params)
            merged.update(draft.extracted_params)
            draft.extracted_params = merged

        status = get_requirement_status()
        return {
            "ok": True,
            "workflow_id": draft.workflow_id,
            "workflow_version": draft.workflow_version,
            "missing_paths": status.get("missing_paths", []),
        }

    def select_capabilities(
        primary_skill: str,
        supporting_skills: Optional[List[str]] = None,
        workflow_type: str = "single",
        reasoning: str = "",
        confidence: float = 0.5,
    ) -> Dict[str, Any]:
        if primary_skill not in capabilities_by_skill:
            return {"ok": False, "error": f"Unknown primary_skill '{primary_skill}'"}
        if workflow_type not in {"single", "parallel", "sequential"}:
            return {"ok": False, "error": f"Invalid workflow_type '{workflow_type}'"}

        normalized_support: List[str] = []
        for skill_id in supporting_skills or []:
            if skill_id == primary_skill:
                continue
            if skill_id not in capabilities_by_skill:
                return {"ok": False, "error": f"Unknown supporting skill '{skill_id}'"}
            if skill_id not in normalized_support:
                normalized_support.append(skill_id)

        draft.primary_skill = primary_skill
        draft.supporting_skills = normalized_support
        draft.workflow_type = workflow_type  # type: ignore[assignment]
        draft.workflow_id = None
        draft.workflow_version = None
        draft.workflow_match_score = None
        draft.selection_source = "dynamic_router"
        draft.reasoning = (reasoning or "").strip()
        draft.confidence = max(0.0, min(1.0, float(confidence)))
        draft.outcome = "agent_plan"
        status = get_requirement_status()
        return {
            "ok": True,
            "primary_skill": draft.primary_skill,
            "supporting_skills": draft.supporting_skills,
            "workflow_type": draft.workflow_type,
            "required_paths": status.get("required_paths", []),
            "missing_paths": status.get("missing_paths", []),
        }

    def set_operation_coverage(
        covered: Optional[List[CoveredOperationInput]] = None,
        unsupported: Optional[List[UnsupportedOperationInput]] = None,
    ) -> Dict[str, Any]:
        operation_ids = {operation.operation_id for operation in draft.operations}
        covered_map: Dict[str, str] = {}
        unsupported_map: Dict[str, str] = {}

        for entry in covered or []:
            operation_id = str(
                entry.operation_id if isinstance(entry, CoveredOperationInput) else entry.get("operation_id", "")
            )
            skill_id = str(
                entry.skill_id if isinstance(entry, CoveredOperationInput) else entry.get("skill_id", "")
            )
            if operation_id not in operation_ids:
                return {"ok": False, "error": f"Unknown operation_id '{operation_id}'"}
            if operation_id in covered_map:
                return {"ok": False, "error": f"Duplicate coverage for '{operation_id}'"}
            if skill_id not in capabilities_by_skill:
                return {"ok": False, "error": f"Unknown skill_id '{skill_id}'"}
            covered_map[operation_id] = skill_id

        for entry in unsupported or []:
            operation_id = str(
                entry.operation_id
                if isinstance(entry, UnsupportedOperationInput)
                else entry.get("operation_id", "")
            )
            reason = str(
                entry.reason if isinstance(entry, UnsupportedOperationInput) else entry.get("reason", "")
            ).strip()
            if operation_id not in operation_ids:
                return {"ok": False, "error": f"Unknown operation_id '{operation_id}'"}
            if operation_id in covered_map or operation_id in unsupported_map:
                return {"ok": False, "error": f"Duplicate coverage for '{operation_id}'"}
            if not reason:
                return {"ok": False, "error": f"Unsupported operation '{operation_id}' needs a reason"}
            unsupported_map[operation_id] = reason

        draft.covered_operations = covered_map
        draft.unsupported_operations = unsupported_map
        uncovered = [
            operation.operation_id
            for operation in draft.operations
            if operation.operation_id not in covered_map
            and operation.operation_id not in unsupported_map
        ]
        return {
            "ok": True,
            "covered_operation_ids": list(covered_map),
            "unsupported_operation_ids": list(unsupported_map),
            "uncovered_operation_ids": uncovered,
        }

    def set_plan_steps(
        steps: List[str],
        estimated_duration_seconds: int = 120,
    ) -> Dict[str, Any]:
        normalized = [str(step).strip() for step in (steps or []) if str(step).strip()]
        draft.steps = normalized
        draft.estimated_duration_seconds = max(1, int(estimated_duration_seconds))
        return {
            "ok": True,
            "steps": draft.steps,
            "estimated_duration_seconds": draft.estimated_duration_seconds,
        }

    def set_user_message(message: str) -> Dict[str, Any]:
        draft.message = str(message or "").strip()
        return {"ok": True, "message": draft.message}

    def finalize_plan() -> Dict[str, Any]:
        operation_ids = [operation.operation_id for operation in draft.operations]
        uncovered = [
            operation_id
            for operation_id in operation_ids
            if operation_id not in draft.covered_operations
            and operation_id not in draft.unsupported_operations
        ]
        if uncovered:
            return {
                "ok": False,
                "error": "Every requested operation must be covered or marked unsupported.",
                "uncovered_operation_ids": uncovered,
            }

        if draft.unsupported_operations:
            draft.outcome = "unsupported"
            draft.primary_skill = None
            draft.supporting_skills = []
            draft.workflow_id = None
            draft.workflow_version = None
            draft.extracted_params = {}
            draft.steps = []
            draft.finalized = True
            return {
                "ok": True,
                "finalized": True,
                "unsupported_operation_ids": list(draft.unsupported_operations),
            }

        if not draft.primary_skill and not draft.workflow_id:
            return {
                "ok": False,
                "error": "No plan selection found. Call select_capabilities or select_workflow_template first.",
            }
        selected = selected_skill_ids()
        unselected_coverage = {
            operation_id: skill_id
            for operation_id, skill_id in draft.covered_operations.items()
            if skill_id not in selected
        }
        if unselected_coverage:
            return {
                "ok": False,
                "error": "Operation coverage references capabilities outside the selected plan.",
                "unselected_coverage": unselected_coverage,
            }

        selected_workflow = get_selected_workflow_candidate()
        sequential = draft.workflow_type == "sequential" or bool(
            selected_workflow and selected_workflow.execution_mode == "sequential"
        )
        skill_positions = {skill_id: index for index, skill_id in enumerate(selected)}
        operations_by_id = {operation.operation_id: operation for operation in draft.operations}
        for operation in draft.operations:
            skill_id = draft.covered_operations.get(operation.operation_id)
            for dependency_id in operation.depends_on:
                dependency_skill = draft.covered_operations.get(dependency_id)
                if not dependency_skill or not skill_id or dependency_skill == skill_id:
                    continue
                if not sequential:
                    return {
                        "ok": False,
                        "error": (
                            "Dependencies covered by different capabilities require a "
                            "sequential workflow."
                        ),
                    }
                if skill_positions[dependency_skill] >= skill_positions[skill_id]:
                    dependency = operations_by_id[dependency_id]
                    return {
                        "ok": False,
                        "error": (
                            "Selected capability order violates operation dependency order: "
                            f"'{dependency.description}' must run before '{operation.description}'."
                        ),
                    }
        status = get_requirement_status()
        missing = status.get("missing_paths", [])
        unresolved_runtime = status.get("unresolved_runtime_paths", [])
        if unresolved_runtime and not get_selected_workflow_candidate():
            return {
                "ok": False,
                "error": (
                    "Selected capabilities require runtime-only inputs that cannot be asked from user. "
                    "Choose a workflow template or different capabilities."
                ),
                "unresolved_runtime_paths": unresolved_runtime,
            }
        draft.outcome = "agent_plan"
        draft.finalized = True
        return {
            "ok": True,
            "finalized": True,
            "missing_paths": missing,
        }

    workflow_tools: List[StructuredTool] = []
    seen_tool_names: set[str] = set()
    for candidate in candidate_list:
        tool_name = candidate.tool_name or workflow_tool_name(candidate.workflow_id)
        if tool_name in seen_tool_names:
            continue
        seen_tool_names.add(tool_name)

        def run_registered_workflow(
            reasoning: str = "",
            confidence: float = 0.8,
            *,
            _candidate: WorkflowPlanningCandidate = candidate,
        ) -> Dict[str, Any]:
            return select_workflow_template(
                workflow_id=_candidate.workflow_id,
                workflow_version=_candidate.workflow_version,
                reasoning=reasoning,
                confidence=confidence,
            )

        label = candidate.display_name or candidate.workflow_id
        summary = candidate.summary or ""
        workflow_tools.append(
            StructuredTool.from_function(
                func=run_registered_workflow,
                name=tool_name,
                description=(
                    f"Select workflow template '{label}' "
                    f"({candidate.workflow_id}@{candidate.workflow_version}). {summary}"
                ).strip(),
                args_schema=SelectRegisteredWorkflowInput,
            )
        )

    planning_tools = [
        StructuredTool.from_function(
            func=select_capabilities,
            name="select_capabilities",
            description="Select the primary/supporting capabilities and workflow type for this request.",
            args_schema=SelectCapabilitiesInput,
        ),
        StructuredTool.from_function(
            func=get_workflow_candidates,
            name="get_workflow_candidates",
            description="Return registered workflow templates available as workflow_* tools.",
        ),
        StructuredTool.from_function(
            func=select_workflow_template,
            name="select_workflow_template",
            description="Select a workflow template candidate by id/version for workflow-template planning.",
            args_schema=SelectWorkflowTemplateInput,
        ),
        StructuredTool.from_function(
            func=get_requirement_status,
            name="get_requirement_status",
            description="Return required parameter paths, missing paths, and schema descriptions for currently selected capabilities.",
        ),
        StructuredTool.from_function(
            func=set_operation_coverage,
            name="set_operation_coverage",
            description=(
                "Map every immutable requested operation to a registered capability, or mark "
                "the operation unsupported with a concrete reason."
            ),
            args_schema=SetOperationCoverageInput,
        ),
        StructuredTool.from_function(
            func=set_plan_steps,
            name="set_plan_steps",
            description="Set user-visible plan steps and estimated duration.",
            args_schema=SetPlanStepsInput,
        ),
        StructuredTool.from_function(
            func=set_user_message,
            name="set_user_message",
            description="Set a concise user-facing planning message.",
            args_schema=SetUserMessageInput,
        ),
        StructuredTool.from_function(
            func=finalize_plan,
            name="finalize_plan",
            description=(
                "Finalize the planning decision after selecting capabilities. Parameter extraction "
                "and missing-input collection run after routing."
            ),
        ),
    ]
    return workflow_tools + planning_tools


def _default_steps_from_selection(
    primary_skill: str,
    supporting_skills: List[str],
    capabilities_by_skill: Dict[str, AgentCapability],
) -> List[str]:
    skills = [primary_skill] + [skill for skill in supporting_skills if skill != primary_skill]
    steps: List[str] = []
    for idx, skill_id in enumerate(skills, 1):
        cap = capabilities_by_skill.get(skill_id)
        label = cap.skill_name if cap else skill_id
        desc = cap.description if cap else "Invoke selected capability"
        steps.append(f"Step {idx}: Invoke '{label}' ({skill_id}) - {desc}")
    return steps


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _planning_tool_schema(tool: StructuredTool) -> Dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if isinstance(args_schema, dict):
        parameters = args_schema
    elif hasattr(args_schema, "model_json_schema"):
        parameters = args_schema.model_json_schema()
    elif hasattr(args_schema, "schema"):
        parameters = args_schema.schema()
    else:
        parameters = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
        },
    }


def _planning_tool_calls(raw: Any) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    choices = _value(raw, "choices", []) or []
    message = _value(choices[0], "message", {}) if choices else {}
    content = _value(message, "content", "")
    raw_calls = _value(message, "tool_calls", []) or []

    assistant_message: Dict[str, Any] = {
        "role": "assistant",
        "content": content or "Planning tool calls requested.",
    }
    tool_calls: List[Dict[str, Any]] = []
    assistant_calls: List[Dict[str, Any]] = []
    for call in raw_calls:
        function = _value(call, "function", {}) or {}
        name = str(_value(function, "name", ""))
        arguments = _value(function, "arguments", {})
        if isinstance(arguments, str):
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_arguments = {}
            wire_arguments = arguments
        elif isinstance(arguments, Mapping):
            parsed_arguments = dict(arguments)
            wire_arguments = json.dumps(parsed_arguments)
        else:
            parsed_arguments = {}
            wire_arguments = "{}"
        call_id = str(_value(call, "id", ""))
        tool_calls.append({"name": name, "args": parsed_arguments, "id": call_id})
        assistant_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": wire_arguments},
            }
        )
    if assistant_calls:
        assistant_message["tool_calls"] = assistant_calls
    return assistant_message, tool_calls


async def compile_plan_with_tools(
    query: str,
    capabilities: List[AgentCapability],
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    operations: Optional[List[RequestedOperation]] = None,
    workflow_candidates: Optional[List[WorkflowPlanningCandidate]] = None,
    forced_workflow_id: Optional[str] = None,
    forced_workflow_version: Optional[str] = None,
    forced_selection_source: Optional[str] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    max_turns: int = 8,
) -> PlanningResult:
    """
    Compile routing/plan decisions using LLM tool calling.

    Who uses this:
    - `chat(...)` in `agent.py` for new user turns and plan refinements.
    """
    history = history or []
    if operations is None:
        decomposition = await decompose_request(
            query=query,
            history=history,
            context=context,
            status_callback=status_callback,
        )
        if decomposition.request_kind != "task":
            return PlanningResult(
                outcome="fallback",
                message=decomposition.message,
            )
        operations = list(decomposition.operations)
    elif not operations:
        raise PlanningContractError(
            "Task planning requires at least one decomposed operation."
        )

    capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}
    draft = _PlanDraft(operations=list(operations))

    if not capabilities_by_skill:
        return PlanningResult(
            outcome="unsupported",
            operations=list(operations),
            unsupported_operations=[
                UnsupportedOperationInput(
                    operation_id=operation.operation_id,
                    reason="No registered capability is available for this operation.",
                )
                for operation in operations
            ],
        )

    candidate_list = list(workflow_candidates or [])
    if forced_workflow_id:
        # If forced selection isn't already present, keep best-effort synthetic candidate.
        exists = any(
            c.workflow_id == forced_workflow_id
            and (forced_workflow_version is None or c.workflow_version == forced_workflow_version)
            for c in candidate_list
        )
        if not exists:
            candidate_list.append(
                WorkflowPlanningCandidate(
                    workflow_id=forced_workflow_id,
                    workflow_version=forced_workflow_version or "",
                    score=1.0,
                    required_paths=[],
                    selection_source=forced_selection_source or "catalog",
                    skills=[],
                    execution_mode="sequential",
                )
            )

    tools = _build_planning_tools(
        draft,
        capabilities_by_skill,
        context=context,
        workflow_candidates=candidate_list,
    )
    tools_by_name = {tool.name: tool for tool in tools}

    system_prompt = SYSTEM_PROMPT
    user_prompt = _build_prompt(
        query=query,
        history=history,
        context=context,
        capabilities=capabilities,
        operations=list(operations),
        workflow_candidates=candidate_list,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tool_schemas = [_planning_tool_schema(tool) for tool in tools]

    async with runtime.create_llm() as llm:
        for _ in range(max(1, max_turns)):
            if status_callback:
                status_callback("Planner LLM evaluating routing/tool calls.")
            response = await llm.medium(
                messages,
                temperature=0,
                max_tokens=2048,
                tools=tool_schemas,
            )
            assistant_message, tool_calls = _planning_tool_calls(response.raw)
            messages.append(assistant_message)

            if not tool_calls:
                if draft.finalized:
                    break
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Planning is not complete. You must set exhaustive operation coverage "
                            "and call finalize_plan."
                        ),
                    }
                )
                continue

            for call in tool_calls:
                tool_name = str(call.get("name"))
                tool_args = call.get("args", {}) or {}
                tool_id = str(call.get("id") or "")
                tool = tools_by_name.get(tool_name)
                if tool is None:
                    tool_result = {"ok": False, "error": f"Unknown tool '{tool_name}'"}
                else:
                    try:
                        tool_result = tool.invoke(tool_args)
                    except Exception as exc:
                        tool_result = {"ok": False, "error": f"{tool_name} failed: {exc}"}

                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, default=str),
                        "tool_call_id": tool_id,
                    }
                )
            if draft.finalized:
                break

    if not draft.finalized:
        raise PlanningContractError(
            f"Planner did not finalize a valid decision within {max(1, max_turns)} turns."
        )

    if draft.outcome == "agent_plan" and draft.primary_skill:
        if not draft.steps:
            draft.steps = _default_steps_from_selection(
                primary_skill=draft.primary_skill,
                supporting_skills=draft.supporting_skills,
                capabilities_by_skill=capabilities_by_skill,
            )
        if not draft.message:
            draft.message = "I've created an execution plan. Please review and confirm."

    return draft.to_result()
