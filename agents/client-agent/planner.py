"""
LLM tool-calling planner for control-plane routing decisions.

`compile_plan_with_tools` is the single entry point. It is called by `chat()`
in `agent.py` whenever a new query needs to be routed. It drives a Claude LLM
through a structured tool-call loop and returns a `PlanningResult` describing
what to do next — no subagents are invoked here.

HOW IT WORKS
------------
1. A `_PlanDraft` accumulates the plan state as the LLM calls tools.
2. The LLM is given:
   - The user query and conversation history
   - Available capabilities (skills + their input schemas)
   - Optional workflow templates (pre-built execution blueprints)
3. The LLM calls planning tools until it calls `finalize_plan` or
   `fallback_to_chat`, at which point the loop exits.
4. The `_PlanDraft` is converted to an immutable `PlanningResult` and returned.

PLANNING TOOLS (called by the LLM, not external code)
------------------------------------------------------
- `select_capabilities`      — choose primary + supporting skills and workflow type
- `workflow_*`              — choose a registered workflow blueprint directly
- `select_workflow_template` — choose a pre-built workflow blueprint by id/version
- `get_workflow_candidates`  — inspect registered workflow options
- `get_requirement_status`   — check which required params are still missing
- `set_extracted_params`     — store param values extracted from the query/context
- `set_plan_steps`           — set human-readable steps shown in the approval UI
- `set_user_message`         — set the planning summary shown to the user
- `finalize_plan`            — commit the plan (validates all required params met)
- `fallback_to_chat`         — respond directly without invoking any skill

OUTCOMES (`PlanningResult.outcome`)
------------------------------------
- `"agent_plan"`  — one or more skills selected; `agent.py` will collect missing
                    params then call `execute_current_plan`
- `"fallback"`    — planner could not or should not invoke a skill; `agent.py`
                    returns the message directly to the user

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

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

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

MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-6")

PROMPTS_DIR = Path(__file__).with_name("prompts")


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = _load_prompt("planner_system.txt")


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


class SetParamsInput(BaseModel):
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted parameter values keyed by input-schema field names",
    )
    merge: bool = Field(
        default=True,
        description="If true, merge into current params. If false, replace params.",
    )


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


class FallbackResponseInput(BaseModel):
    message: str = Field(
        description="Direct assistant response when no capability should be invoked",
    )


class PlanningResult(BaseModel):
    """Structured planner output consumed by `agent.py` chat flow."""

    outcome: Literal["agent_plan", "fallback"] = "agent_plan"
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


@dataclass
class _PlanDraft:
    """Mutable draft updated via planning tools during a single planning session."""

    outcome: Literal["agent_plan", "fallback"] = "agent_plan"
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

    def set_extracted_params(params: Dict[str, Any], merge: bool = True) -> Dict[str, Any]:
        if merge:
            merged = dict(draft.extracted_params)
            merged.update(dict(params or {}))
            draft.extracted_params = merged
        else:
            draft.extracted_params = dict(params or {})
        status = get_requirement_status()
        return {
            "ok": True,
            "params": draft.extracted_params,
            "missing_paths": status.get("missing_paths", []),
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
        if not draft.primary_skill and not draft.workflow_id:
            return {
                "ok": False,
                "error": "No plan selection found. Call select_capabilities or select_workflow_template first.",
            }
        status = get_requirement_status()
        missing = status.get("missing_paths", [])
        unresolved_runtime = status.get("unresolved_runtime_paths", [])
        if missing:
            return {
                "ok": False,
                "error": "Required fields are still missing.",
                "missing_paths": missing,
            }
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

    def fallback_to_chat(message: str) -> Dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            return {"ok": False, "error": "Fallback message must not be empty."}
        draft.outcome = "fallback"
        draft.message = text
        draft.primary_skill = None
        draft.supporting_skills = []
        draft.extracted_params = {}
        draft.steps = []
        draft.finalized = True
        return {"ok": True, "finalized": True}

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
            func=set_extracted_params,
            name="set_extracted_params",
            description="Set or update parameters extracted from the user request for the selected capability.",
            args_schema=SetParamsInput,
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
            description="Finalize the planning decision after selecting capabilities and parameters.",
        ),
        StructuredTool.from_function(
            func=fallback_to_chat,
            name="fallback_to_chat",
            description="Finalize a direct conversational response when no capability invocation is needed.",
            args_schema=FallbackResponseInput,
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


async def compile_plan_with_tools(
    query: str,
    capabilities: List[AgentCapability],
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
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
    capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}
    draft = _PlanDraft()

    if not capabilities_by_skill:
        return PlanningResult(
            outcome="fallback",
            message="No capabilities are available right now. Please try again shortly.",
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
        workflow_candidates=candidate_list,
    )

    llm = ChatAnthropic(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=2048,
    ).bind_tools(tools)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    for _ in range(max(1, max_turns)):
        if status_callback:
            status_callback("Planner LLM evaluating routing/tool calls.")
        ai_message = await asyncio.to_thread(llm.invoke, messages)
        messages.append(ai_message)

        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            if draft.finalized:
                break
            messages.append(
                HumanMessage(
                    content=(
                        "Planning is not complete. You must call finalize_plan for an agent plan "
                        "or fallback_to_chat for a direct answer."
                    )
                )
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
                ToolMessage(
                    content=json.dumps(tool_result, default=str),
                    tool_call_id=tool_id,
                )
            )
        if draft.finalized:
            break

    if not draft.finalized and not draft.primary_skill and not draft.workflow_id:
        return PlanningResult(
            outcome="fallback",
            message="I could not determine a reliable capability plan for that request.",
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
