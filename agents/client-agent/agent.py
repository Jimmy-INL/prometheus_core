"""
Client Agent - Orchestrates nuclear analysis workflows
Uses deterministic execution with tool-based planning decisions.
"""
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.requests import Request
from prometheus_api.agent import ArtifactReference, EventQueue, PrometheusAgent, RequestContext

# Add shared module to path
sys.path.insert(0, "/app")

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from artifact_handling import (
    merge_artifact_catalogs,
    merge_artifacts_into_context,
    resolve_artifact_inputs,
    summarize_artifacts_for_context,
)
from tool_discovery import get_all_tools_dynamic
from capability_cache import get_capability_cache
from param_schema import (
    extract_required_param_paths,
    flatten_schema_properties,
    get_nested_value,
    has_param_path,
    is_user_input_schema,
    normalize_params_for_input_schema,
    set_nested_value,
)
from planner import PlanningResult, WorkflowPlanningCandidate, compile_plan_with_tools
from workflow_library import execute_workflow, get_workflow_registry, match_workflows
from conversation_store import get_conversation, store_conversation

AGENT_PORT = int(os.getenv("AGENT_PORT", "8000"))
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")
DISCOVERY_REFRESH_SECONDS = int(os.getenv("DISCOVERY_REFRESH_SECONDS", "300"))
ENABLE_WORKFLOW_LIBRARY = os.getenv("ENABLE_WORKFLOW_LIBRARY", "true").lower() in {"1", "true", "yes"}

# Global tools cache (populated on startup)
_tools_cache = None
_refresh_task: Optional[asyncio.Task] = None
_refresh_lock: Optional[asyncio.Lock] = None
_status_redis_client: Any = None


# NEW: Conversational interface models
class ConversationRequest(BaseModel):
    query: Optional[str] = ""                    # Natural language query (optional for followup/approval)
    conversation_id: Optional[str] = None        # For multi-turn
    followup_answers: Optional[Dict] = None      # Answers to followup questions
    plan_approved: Optional[bool] = False        # Approval to execute plan
    artifacts: Optional[List[Dict[str, Any]]] = None  # Conversation artifact references (metadata only)
    workflow_id: Optional[str] = None            # Explicit workflow template selection
    workflow_version: Optional[str] = None       # Optional explicit workflow version
    selection_source: Optional[str] = None       # catalog|matcher|dynamic_router


class ConversationResponse(BaseModel):
    conversation_id: str
    status: str  # "needs_info" | "plan_ready" | "executing" | "completed" | "recommendation" | "answer"
    message: Optional[str] = None

    # When status == "needs_info"
    followup_questions: Optional[List[Dict]] = None

    # When status == "plan_ready"
    plan: Optional[Dict] = None

    # When status == "completed"
    report: Optional[str] = None
    tool_results: Optional[Dict] = None

    # When status == "recommendation" or "answer"
    response_text: Optional[str] = None
    recommended_materials: Optional[List[str]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None
    message_metadata: Optional[Dict[str, Any]] = None


class AgentState(TypedDict):
    """State for a conversation's orchestration lifecycle."""
    messages: List[Dict[str, Any]]

    # Conversation tracking
    conversation_id: Optional[str]
    user_query: Optional[str]
    conversation_history: List[Dict]

    # Dynamic routing decision
    routing_decision: Optional[Dict[str, Any]]  # Full RoutingDecision.to_dict()

    # Planning phase
    plan: Optional[Dict]
    missing_info: List[str]
    awaiting_approval: bool
    pending_subagent_request: Optional[Dict[str, Any]]

    # Query parameters (extracted from routing decision)
    material_id: Optional[str]
    analysis_types: Optional[List[str]]
    context: Optional[Dict[str, Any]]
    question: Optional[str]

    # Results
    tool_results: Dict[str, Any]
    final_report: Optional[str]


def create_llm():
    """Create the Claude LLM instance."""
    return ChatAnthropic(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=4096,
    )


def _get_status_redis_client():
    """Lazy Redis client for status history updates."""
    global _status_redis_client
    if _status_redis_client is None:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _status_redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _status_redis_client


def store_status_update(conversation_id: Optional[str], message: str, final: bool = False) -> None:
    """Store a status message in Redis for frontend progress rendering."""
    conv_id = str(conversation_id or "").strip()
    text = str(message or "").strip()
    if not conv_id or not text:
        return

    try:
        status_data = {
            "message": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "final": final,
        }
        redis_client = _get_status_redis_client()
        redis_client.setex(f"agent:status:{conv_id}", 900, json.dumps(status_data))
        history_key = f"agent:status_history:{conv_id}"
        redis_client.rpush(history_key, json.dumps(status_data))
        redis_client.ltrim(history_key, -300, -1)
        redis_client.expire(history_key, 900)
    except Exception as exc:
        print(f"[STATUS] Failed to store status update: {exc}")


async def initialize_tools():
    """Initialize tools on startup - called once.

    Discovers tools dynamically from the registry by querying
    registered agents and their capabilities.
    """
    global _tools_cache

    print("Discovering tools from registry...")
    _tools_cache = await get_all_tools_dynamic()
    print(f"Initialized {len(_tools_cache)} tools")


def get_refresh_lock() -> asyncio.Lock:
    """Get a singleton lock used for coordinated discovery refresh."""
    global _refresh_lock
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
    return _refresh_lock


async def refresh_dynamic_components(trigger: str = "manual") -> Dict[str, Any]:
    """Refresh discovery-dependent runtime components."""
    lock = get_refresh_lock()
    async with lock:
        print(f"Refreshing dynamic components (trigger={trigger})...")
        await initialize_tools()
        cache = get_capability_cache()
        await cache.refresh()
        workflow_refresh = None
        if ENABLE_WORKFLOW_LIBRARY:
            registry = get_workflow_registry()
            capabilities = await cache.get_capabilities()
            workflow_refresh = registry.refresh(capabilities)
        return {
            "status": "ok",
            "trigger": trigger,
            "tools": len(_tools_cache or []),
            "workflow_library": workflow_refresh,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def discovery_refresh_loop() -> None:
    """Periodically refresh tools and capability cache for runtime discovery."""
    interval = max(30, DISCOVERY_REFRESH_SECONDS)
    while True:
        await asyncio.sleep(interval)
        try:
            await refresh_dynamic_components(trigger="background")
        except Exception as e:
            print(f"[WARN] Background discovery refresh failed: {e}")


def create_tools():
    """Get all available analysis tools from cache."""
    if _tools_cache is None:
        raise RuntimeError("Tools not initialized. Call initialize_tools() first.")
    return _tools_cache


def extract_json_from_text(text: str):
    """Extract JSON from text that may contain markdown code blocks or extra text.

    Returns: Parsed JSON (can be dict, list, or other JSON type) or None
    """
    import re

    # Try to find JSON in code blocks first (objects or arrays)
    json_match = re.search(r'```json\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON array
    json_match = re.search(r'\[.*\]', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def get_selected_skills(routing_decision: Optional[Dict[str, Any]]) -> List[str]:
    """Return a stable, deduplicated ordered list of skills to invoke."""
    if not routing_decision:
        return []
    skills: List[str] = []
    primary = routing_decision.get("primary_skill")
    if primary:
        skills.append(primary)
    for skill in routing_decision.get("supporting_skills", []):
        if skill and skill not in skills:
            skills.append(skill)
    return skills


async def resolve_user_required_params(routing_decision: Optional[Dict[str, Any]]) -> List[str]:
    """Resolve user-provided required params for the current routing decision."""
    if not routing_decision:
        return []

    workflow_type = routing_decision.get("workflow_type")
    workflow_id = routing_decision.get("workflow_id")
    workflow_version = routing_decision.get("workflow_version")
    if workflow_type == "workflow_template" and workflow_id and ENABLE_WORKFLOW_LIBRARY:
        workflow = get_workflow_registry().get(str(workflow_id), version=workflow_version)
        if workflow:
            return sorted(set(workflow.required_input_paths))

    cache = get_capability_cache()
    required: set[str] = set()
    for skill_id in get_selected_skills(routing_decision):
        capability = await cache.get_capability_by_skill_id(skill_id)
        if not capability:
            continue
        required.update(extract_required_param_paths(capability.input_schema))

    if required:
        return sorted(required)
    return sorted(set(routing_decision.get("required_params", []) or []))


def extract_material_ids_from_text(text: str) -> List[str]:
    """Extract material identifiers like SS316/ss347 from free text."""
    if not text:
        return []
    ids: List[str] = []

    def add(material_id: str) -> None:
        normalized = material_id.upper().replace(" ", "")
        if normalized and normalized not in ids:
            ids.append(normalized)

    # SS316, ss347, SS 316, SS-316L
    for match in re.finditer(r"\bss[\s-]*(\d{3}[a-z]?)\b", text, flags=re.IGNORECASE):
        add(f"SS{match.group(1)}")

    # Stainless steel 316 / stainless steel 347
    for match in re.finditer(r"\bstainless\s+steel\s*(\d{3}[a-z]?)\b", text, flags=re.IGNORECASE):
        add(f"SS{match.group(1)}")

    return ids


def enrich_material_params(query: str, extracted_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Infer and normalize material parameters from query and extracted params."""
    params = dict(extracted_params or {})

    candidate_texts: List[str] = [query or ""]
    material_id = params.get("material_id")
    if isinstance(material_id, str):
        candidate_texts.append(material_id)
    material_ids = params.get("material_ids")
    if isinstance(material_ids, list):
        candidate_texts.extend(str(value) for value in material_ids if value is not None)

    inferred: List[str] = []
    for text in candidate_texts:
        for parsed in extract_material_ids_from_text(text):
            if parsed not in inferred:
                inferred.append(parsed)

    if inferred:
        params["material_ids"] = inferred
        params["material_id"] = inferred[0]

    return params


def order_skills_for_workflow(routing_decision: Optional[Dict[str, Any]]) -> List[str]:
    """Return selected skills ordered for the requested workflow semantics.

    For sequential workflows, orders skills based on metadata from agent cards:
    - execution_priority: "early", "normal", or "late"
    - usage_notes: Explicit hints like "call this first"
    - provides/derivation_rules: Skills that provide context run before consumers

    This is fully data-driven - no hardcoded domain knowledge about what skills do.

    Args:
        routing_decision: Dict with workflow_type and selected skills

    Returns:
        List of skill_ids in execution order
    """
    skills = get_selected_skills(routing_decision)
    if not skills or len(skills) <= 1:
        return skills
    if not routing_decision or routing_decision.get("workflow_type") != "sequential":
        return skills

    cache = get_capability_cache()
    scored: List[Any] = []

    # Build map of which skills provide context keys
    providers: Dict[str, List[str]] = {}  # context_key -> [skill_ids that provide it]
    for skill_id in skills:
        capability = cache.get_by_skill_id(skill_id)
        if capability and capability.provides:
            for provide_rule in capability.provides:
                if isinstance(provide_rule, dict) and provide_rule.get("type") == "context_map":
                    context_key = provide_rule.get("context_key")
                    if context_key:
                        if context_key not in providers:
                            providers[context_key] = []
                        providers[context_key].append(skill_id)

    for idx, skill_id in enumerate(skills):
        capability = cache.get_by_skill_id(skill_id)
        usage_notes = (capability.usage_notes or "").lower() if capability else ""

        # Lower score means earlier execution
        score = idx * 100  # Preserve original order by default

        # 1. Use execution_priority from agent card metadata
        if capability and capability.execution_priority:
            priority_map = {"early": -500, "normal": 0, "late": 500}
            score += priority_map.get(capability.execution_priority, 0)

        # 2. Explicit prerequisite hint from usage_notes
        if "always call this first" in usage_notes or "call this first" in usage_notes:
            score -= 1000

        # 3. Skills that provide context should run before skills that consume it
        if capability and capability.provides:
            score -= 200  # Provider skills run early

        # 4. Skills with derivation rules are consumers, should run later
        if capability and capability.derivation_rules:
            # Check if this skill derives params from context maps
            for rule in capability.derivation_rules:
                if isinstance(rule, dict):
                    derive = rule.get("derive", {})
                    if isinstance(derive, dict) and derive.get("type") == "from_context_map":
                        context_key = derive.get("context_key")
                        # If there's a provider for this context in the selected skills, run after it
                        if context_key and context_key in providers:
                            score += 300
                            break

        scored.append((score, idx, skill_id))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [skill_id for _, _, skill_id in scored]


def _humanize_param_path(path: str) -> str:
    """Convert dotted param path into a readable fallback label."""
    token = str(path or "").split(".")[-1]
    return token.replace("_", " ").strip().capitalize() or str(path)


def build_plan_param_metadata(
    selected_skills: List[str],
    capabilities_by_skill: Dict[str, Any],
    selected_workflow: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Build UI-friendly param metadata (label/description/type/unit) for plan display."""
    metadata: Dict[str, Dict[str, Any]] = {}
    properties: Dict[str, Dict[str, Any]] = {}

    for skill_id in selected_skills:
        capability = capabilities_by_skill.get(skill_id)
        if not capability:
            continue
        properties.update(flatten_schema_properties(capability.input_schema))

    for path, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        is_object = prop.get("type") == "object" or "properties" in prop
        if is_object:
            continue
        metadata[path] = {
            "label": str(prop.get("title") or _humanize_param_path(path)),
            "description": str(prop.get("description") or "").strip(),
            "type": prop.get("type"),
            "unit": prop.get("unit"),
        }

    if selected_workflow is not None:
        overrides = (selected_workflow.definition.ui.input_overrides or {})
        for path, override in overrides.items():
            entry = dict(metadata.get(path, {}))
            label = getattr(override, "label", None)
            description = getattr(override, "description", None)
            field_type = getattr(override, "type", None)
            unit = getattr(override, "unit", None)

            if label:
                entry["label"] = str(label)
            elif "label" not in entry:
                entry["label"] = _humanize_param_path(path)

            if description:
                entry["description"] = str(description).strip()
            elif "description" not in entry:
                entry["description"] = ""

            if field_type:
                entry["type"] = field_type
            if unit:
                entry["unit"] = unit
            metadata[path] = entry

    return metadata


def extract_result_text(result_data: Any) -> str:
    """Extract human-readable text from common agent response formats."""
    if isinstance(result_data, dict):
        for key in ("answer", "response", "report", "message", "result", "raw_response"):
            value = result_data.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if value and not isinstance(value, (dict, list)):
                return str(value)
        return json.dumps(result_data, indent=2)
    return str(result_data)


def normalize_suggested_queries(raw: Any, limit: int = 3) -> List[Dict[str, str]]:
    """Normalize suggested query payloads into UI-friendly metadata entries."""
    if not isinstance(raw, list):
        return []

    results: List[Dict[str, str]] = []
    seen = set()
    for item in raw:
        if isinstance(item, dict):
            query = str(item.get("suggested_query") or item.get("query") or "").strip()
        else:
            query = str(item or "").strip()
        if not query:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({"suggested_query": query})
        if len(results) >= limit:
            break
    return results


def collect_suggested_queries(tool_results: Dict[str, Any], limit: int = 3) -> List[Dict[str, str]]:
    """Collect deduplicated suggested queries from skill result payloads."""
    merged: List[Dict[str, str]] = []
    seen = set()
    for result_data in tool_results.values():
        if not isinstance(result_data, dict):
            continue
        for suggestion in normalize_suggested_queries(result_data.get("suggested_queries"), limit=limit):
            query = suggestion.get("suggested_query", "")
            key = query.lower()
            if not query or key in seen:
                continue
            seen.add(key)
            merged.append({"suggested_query": query})
            if len(merged) >= limit:
                return merged
    return merged


def build_comparison_summary(user_query: str, by_material: Dict[str, Any]) -> Optional[str]:
    """Build deterministic comparison text for common comparison queries."""
    if not by_material or len(by_material) < 2:
        return None
    q = (user_query or "").lower()

    if "temperature" in q and ("max" in q or "maximum" in q):
        rows = []
        for material_id, result in by_material.items():
            data = result.get("material_data", {}) if isinstance(result, dict) else {}
            env = data.get("operating_environment", {}) if isinstance(data, dict) else {}
            temp_range = env.get("temperature_range_c")
            max_temp = None
            if isinstance(temp_range, list) and len(temp_range) >= 2:
                max_temp = temp_range[1]
            rows.append((material_id, max_temp))

        known = [r for r in rows if r[1] is not None]
        if not known:
            return None
        known.sort(key=lambda item: item[1], reverse=True)

        lines = ["Comparison (maximum operating temperature):"]
        for material_id, max_temp in known:
            lines.append(f"- {material_id}: {max_temp} C")
        if len(known) >= 2:
            delta = known[0][1] - known[-1][1]
            lines.append(f"Difference between highest and lowest: {delta} C")
        return "\n".join(lines)

    return None


def normalize_by_mode(value: Any, mode: Optional[str]) -> Any:
    """Normalize values based on a metadata-specified mode."""
    if mode == "upper_no_space_hyphen" and isinstance(value, str):
        return value.upper().replace(" ", "").replace("-", "")
    return value


def get_value_by_path(data: Any, path: Optional[str]) -> Any:
    """Read dotted path from dict/list structures, supporting numeric list indexes."""
    if not path:
        return data
    current = data
    for token in path.split("."):
        if isinstance(current, dict):
            if token not in current:
                return None
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                return None
            idx = int(token)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        return None
    return current


def set_param_path(params: Dict[str, Any], path: str, value: Any) -> None:
    """Set a derived parameter on both dotted and nested forms."""
    if "." in path:
        set_nested_value(params, path, value)
    params[path] = value


def rule_matches_query(query: str, rule: Dict[str, Any]) -> bool:
    """Check metadata rule query conditions."""
    when = rule.get("when", {})
    if not isinstance(when, dict):
        return True
    phrases_any = when.get("phrases_any")
    if not phrases_any:
        return True
    q = (query or "").lower()
    return any(str(phrase).lower() in q for phrase in phrases_any)


def merge_context_map(target_context: Dict[str, Any], context_key: str, entries: Dict[str, Any]) -> None:
    """Merge entries into a context map key (supports dotted context key paths)."""
    if not entries:
        return
    existing = get_nested_value(target_context, context_key)
    existing_map = existing if isinstance(existing, dict) else {}
    merged = {**existing_map, **entries}
    if "." in context_key:
        set_nested_value(target_context, context_key, merged)
    else:
        target_context[context_key] = merged


def extract_provided_context_maps(
    result_data: Any,
    provides: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Extract context-map entries from a skill result using metadata rules.

    Context maps enable data sharing between skills in sequential workflows.
    A skill can declare that it "provides" certain context (e.g., material_max_temps)
    which downstream skills can then derive parameters from.

    This function applies metadata-defined extraction rules from the agent card's
    "provides" field to extract key-value pairs from the skill result.

    Example rule:
    {
        "type": "context_map",
        "context_key": "material_max_temps",
        "item_key_path": "material_id",
        "item_value_path": "operating_environment.temperature_range_c.1",
        "key_normalizer": "upper_no_space_hyphen",
        "value_type": "number"
    }

    Args:
        result_data: The skill invocation result
        provides: List of context_map rules from agent card

    Returns:
        Dict mapping context_key to extracted key-value pairs
    """
    extracted: Dict[str, Dict[str, Any]] = {}
    if not isinstance(result_data, dict):
        return extracted

    for rule in provides or []:
        if not isinstance(rule, dict) or rule.get("type") != "context_map":
            continue

        context_key = rule.get("context_key")
        item_key_path = rule.get("item_key_path")
        item_value_path = rule.get("item_value_path")
        key_normalizer = rule.get("key_normalizer")
        value_type = rule.get("value_type")
        if not context_key or not item_value_path:
            continue

        # Extract entries from result (handles both single-item and by_material batch results)
        entries: Dict[str, Any] = {}
        candidates: List[Any] = [result_data]
        by_material = result_data.get("by_material")
        if isinstance(by_material, dict):
            candidates = list(by_material.values())

        for candidate in candidates:
            # Extract key (e.g., material_id)
            key_value = get_value_by_path(candidate, item_key_path)
            if key_value is None and isinstance(candidate, dict):
                key_value = candidate.get("material_id")
            if key_value is None:
                continue

            # Extract value (e.g., max temperature)
            value = get_value_by_path(candidate, item_value_path)
            if value is None:
                continue
            if value_type == "number" and not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except Exception:
                    continue

            # Normalize key (e.g., "SS-316L" → "SS316L")
            normalized_key = normalize_by_mode(key_value, key_normalizer)
            if normalized_key is None:
                continue
            entries[str(normalized_key)] = value

        if entries:
            existing = extracted.get(context_key, {})
            extracted[context_key] = {**existing, **entries}

    return extracted


def collect_context_maps_from_history(
    conversation_history: List[Dict[str, Any]],
    capabilities_by_skill: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Rebuild context maps from prior tool results using capability metadata.

    In multi-turn conversations, we need to remember context provided by earlier
    skill invocations. This function replays the conversation history and re-extracts
    all context maps using the same metadata rules that were applied originally.

    This enables parameter derivation in later turns to use data from earlier turns
    (e.g., using max_temp retrieved in turn 1 for analysis in turn 2).

    Args:
        conversation_history: List of conversation messages with tool_results
        capabilities_by_skill: Map of skill_id to AgentCapability with "provides" metadata

    Returns:
        Aggregated context maps from all history
    """
    aggregated: Dict[str, Dict[str, Any]] = {}
    for message in conversation_history or []:
        tool_results = message.get("tool_results")
        if not isinstance(tool_results, dict):
            continue
        for skill_id, result_data in tool_results.items():
            capability = capabilities_by_skill.get(skill_id)
            if not capability:
                continue
            # Re-extract context maps using capability metadata
            extracted = extract_provided_context_maps(result_data, capability.provides)
            for context_key, entries in extracted.items():
                current = aggregated.get(context_key, {})
                aggregated[context_key] = {**current, **entries}
    return aggregated


def derive_params_from_rules(
    query: str,
    params: Dict[str, Any],
    rules: List[Dict[str, Any]],
    context: Dict[str, Any],
    history_context_maps: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Derive missing parameter values from metadata-defined derivation rules.

    Derivation rules enable skills to automatically populate parameters from context
    without user input. For example, a rule might say "derive max_temperature from
    the material_max_temps context map using material_id as the lookup key."

    Example derivation rule:
    {
        "target_param": "context.max_temperature_c",
        "derive": {
            "type": "from_context_map",
            "context_key": "material_max_temps",
            "lookup_key_param": "material_id",
            "key_normalizer": "upper_no_space_hyphen",
            "value_type": "number"
        },
        "when": {"phrases_any": ["maximum", "max temp"]}
    }

    Args:
        query: User query (for conditional rule matching)
        params: Current parameters
        rules: Derivation rules from agent card
        context: Current context with context maps
        history_context_maps: Context maps from conversation history

    Returns:
        Parameters with derived values added
    """
    derived = dict(params)

    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        target_param = rule.get("target_param")
        derive = rule.get("derive", {})
        if not target_param or not isinstance(derive, dict):
            continue
        # Skip if parameter already has a value
        if has_param_path(derived, target_param):
            continue
        # Check rule conditions (e.g., "when query contains 'maximum'")
        if not rule_matches_query(query, rule):
            continue

        # Currently only supports "from_context_map" derivation type
        if derive.get("type") != "from_context_map":
            continue

        context_key = derive.get("context_key")
        lookup_key_param = derive.get("lookup_key_param", "material_id")
        key_normalizer = derive.get("key_normalizer")
        value_type = derive.get("value_type")
        if not context_key:
            continue

        # Get the lookup key value (e.g., "SS316" from params["material_id"])
        lookup_key = get_nested_value(derived, lookup_key_param)
        if lookup_key is None:
            lookup_key = derived.get(lookup_key_param)
        if isinstance(lookup_key, list) and lookup_key:
            lookup_key = lookup_key[0]
        lookup_key = normalize_by_mode(lookup_key, key_normalizer)
        if lookup_key is None:
            continue

        # Look up value in context map (merged with history)
        value_map = get_nested_value(context, context_key)
        map_data: Dict[str, Any] = value_map if isinstance(value_map, dict) else {}
        if context_key in history_context_maps:
            map_data = {**history_context_maps[context_key], **map_data}

        value = map_data.get(str(lookup_key))
        if value is None:
            continue
        # Type conversion if needed
        if value_type == "number" and not isinstance(value, (int, float)):
            try:
                value = float(value)
            except Exception:
                continue

        # Set the derived parameter
        set_param_path(derived, target_param, value)

    return derived


async def resolve_params_via_capability_metadata(
    query: str,
    extracted_params: Optional[Dict[str, Any]],
    selected_skills: List[str],
    context: Optional[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve missing params using capability `derivation_rules` metadata.

    This is the core parameter resolution engine that enables fully data-driven workflows.
    It performs a multi-step process to automatically derive missing parameters:

    1. Rebuild context maps from conversation history
    2. Carry forward known context fields into params
    3. Identify which context maps are needed for pending derivation rules
    4. Prefetch missing context by invoking provider skills (if safe/no-approval)
    5. Apply derivation rules to populate missing parameters

    This enables complex workflows where:
    - Skill A provides data (e.g., max_temperature)
    - Skill B derives parameters from that data (e.g., for analysis)
    - All without hardcoded logic - purely driven by agent card metadata

    Args:
        query: User query
        extracted_params: Parameters extracted from query
        selected_skills: Skills selected by routing decision
        context: Current context state
        conversation_history: Previous conversation turns

    Returns:
        Parameters with derived values added
    """
    params = dict(extracted_params or {})
    if not selected_skills:
        return params

    # Step 1: Look up capability metadata for selected skills
    cache = get_capability_cache()
    capabilities_by_skill: Dict[str, Any] = {}
    for skill_id in selected_skills:
        capability = await cache.get_capability_by_skill_id(skill_id)
        if capability:
            capabilities_by_skill[skill_id] = capability

    # Include all provider skills for history reconstruction
    # (even if not currently selected, we need their context maps from history)
    all_capabilities = await cache.get_capabilities()
    for capability in all_capabilities:
        if capability.provides and capability.skill_id not in capabilities_by_skill:
            capabilities_by_skill[capability.skill_id] = capability

    if not capabilities_by_skill:
        return params

    # Step 2: Rebuild context maps from conversation history
    history_context_maps = collect_context_maps_from_history(
        conversation_history,
        capabilities_by_skill,
    )
    merged_context = dict(context or {})
    for context_key, entries in history_context_maps.items():
        merge_context_map(merged_context, context_key, entries)

    # Step 3: Build effective query including recent user intents for rule matching
    recent_user_intents = [
        str(msg.get("content", ""))
        for msg in (conversation_history or [])[-8:]
        if msg.get("role") == "user" and msg.get("content")
    ]
    effective_query = " ".join([query or "", *recent_user_intents]).strip()
    if not effective_query:
        effective_query = query or ""

    # Step 4: Carry forward known context fields into params for required context.* paths
    selected_input_schemas: List[Dict[str, Any]] = []
    for skill_id in selected_skills:
        capability = capabilities_by_skill.get(skill_id)
        if not capability:
            continue
        if isinstance(capability.input_schema, dict):
            selected_input_schemas.append(capability.input_schema)
        required_paths = extract_required_param_paths(capability.input_schema)
        for path in required_paths:
            if not path.startswith("context.") or has_param_path(params, path):
                continue
            value = get_nested_value(merged_context, path)
            if value is not None:
                set_param_path(params, path, value)

    # Step 4b: Resolve declared artifact-reference params from conversation artifact metadata.
    params = resolve_artifact_inputs(
        params=params,
        query=effective_query,
        context=merged_context,
        input_schemas=selected_input_schemas,
    )

    # Step 5: Identify pending derivation rules and needed context maps
    pending_rules: List[Dict[str, Any]] = []
    for skill_id in selected_skills:
        capability = capabilities_by_skill.get(skill_id)
        if not capability:
            continue
        for rule in capability.derivation_rules or []:
            if not isinstance(rule, dict):
                continue
            target_param = rule.get("target_param")
            derive = rule.get("derive", {})
            if not target_param or not isinstance(derive, dict):
                continue
            if derive.get("type") != "from_context_map":
                continue
            if has_param_path(params, target_param):
                continue
            if not rule_matches_query(effective_query, rule):
                continue
            pending_rules.append(rule)

    needed_context_keys = {
        rule.get("derive", {}).get("context_key")
        for rule in pending_rules
        if isinstance(rule.get("derive"), dict)
    }
    needed_context_keys = {
        key for key in needed_context_keys
        if key and (
            not isinstance(get_nested_value(merged_context, key), dict)
            or not get_nested_value(merged_context, key)
        )
    }

    # Step 6: Metadata-driven prefetch - invoke provider skills to populate needed context
    # Only invoke skills that don't require approval and whose params are satisfied
    if needed_context_keys:
        for skill_id, capability in capabilities_by_skill.items():
            if not capability or capability.requires_approval or not capability.provides:
                continue
            provided_keys = {
                p.get("context_key")
                for p in capability.provides
                if isinstance(p, dict) and p.get("type") == "context_map" and p.get("context_key")
            }
            if not provided_keys.intersection(needed_context_keys):
                continue

            required_paths = extract_required_param_paths(capability.input_schema)
            if not all(has_param_path(params, path) for path in required_paths):
                continue

            # Prefetch: invoke the provider skill
            prefetched = await invoke_skill(
                skill_id,
                params,
                conversation_id=f"prefetch-{uuid.uuid4()}",
                emit_status=False,
            )
            if "result" not in prefetched:
                continue

            # Extract and merge context maps from prefetch result
            extracted_maps = extract_provided_context_maps(prefetched["result"], capability.provides)
            for context_key, entries in extracted_maps.items():
                merge_context_map(merged_context, context_key, entries)
                current = history_context_maps.get(context_key, {})
                history_context_maps[context_key] = {**current, **entries}

            # Update needed keys
            needed_context_keys = {
                key for key in needed_context_keys
                if (
                    not isinstance(get_nested_value(merged_context, key), dict)
                    or not get_nested_value(merged_context, key)
                )
            }
            if not needed_context_keys:
                break

    # Step 7: Apply derivation rules to populate missing parameters
    for skill_id in selected_skills:
        capability = capabilities_by_skill.get(skill_id)
        if not capability:
            continue
        params = derive_params_from_rules(
            query=effective_query,
            params=params,
            rules=capability.derivation_rules,
            context=merged_context,
            history_context_maps=history_context_maps,
        )

    return params


async def find_tool_for_skill(skill_id: str, refresh_on_miss: bool = True):
    """Find tool by skill id and optionally refresh discovery once on cache miss."""
    for tool in create_tools():
        if tool.name == skill_id:
            return tool

    if refresh_on_miss:
        await refresh_dynamic_components(trigger=f"tool_miss:{skill_id}")
        for tool in create_tools():
            if tool.name == skill_id:
                return tool

    return None


async def invoke_skill(
    skill_id: str,
    params: Dict[str, Any],
    conversation_id: str,
    emit_status: bool = True,
) -> Dict[str, Any]:
    """Invoke a single discovered skill with validation and normalized output."""
    if emit_status:
        store_status_update(conversation_id, f"Invoking '{skill_id}'.")
    tool = await find_tool_for_skill(skill_id, refresh_on_miss=True)
    if not tool:
        if emit_status:
            store_status_update(conversation_id, f"Capability '{skill_id}' is currently unavailable.")
        return {
            "skill_id": skill_id,
            "error": f"Capability '{skill_id}' is not currently available.",
        }

    cache = get_capability_cache()
    capability = await cache.get_capability_by_skill_id(skill_id)

    required_params = extract_required_param_paths(capability.input_schema) if capability else []
    material_ids = params.get("material_ids")

    async def invoke_once(single_params: Dict[str, Any]) -> Dict[str, Any]:
        input_schema = capability.input_schema if capability else None
        invoke_params = normalize_params_for_input_schema(dict(single_params), input_schema=input_schema)
        invoke_params["conversation_id"] = conversation_id
        missing = [param for param in required_params if not has_param_path(invoke_params, param)]
        if missing:
            if emit_status:
                store_status_update(
                    conversation_id,
                    f"Missing required parameters for '{skill_id}': {', '.join(missing)}.",
                )
            return {
                "error": f"Missing required parameters for '{skill_id}': {missing}",
                "missing_required_params": missing,
            }
        try:
            raw_result = await tool.ainvoke(invoke_params)
            if isinstance(raw_result, str):
                try:
                    result_data = json.loads(raw_result)
                except json.JSONDecodeError:
                    result_data = {"raw_response": raw_result}
            else:
                result_data = raw_result
            if isinstance(result_data, dict) and result_data.get("status") == "input_required":
                return {
                    "input_required": result_data.get("input_required", {}),
                    "_a2a_context_id": result_data.get("_a2a_context_id"),
                    "_a2a_task_id": result_data.get("_a2a_task_id"),
                }
            if isinstance(result_data, dict) and result_data.get("error"):
                missing = [param for param in required_params if not has_param_path(invoke_params, param)]
                payload = {"error": str(result_data.get("error"))}
                if missing:
                    payload["missing_required_params"] = missing
                return payload
            if emit_status:
                store_status_update(conversation_id, f"'{skill_id}' completed.")
            return {"result": result_data}
        except Exception as e:
            if emit_status:
                store_status_update(conversation_id, f"'{skill_id}' failed: {e}")
            return {"error": str(e)}

    # Batch path for comparison-style queries with multiple material IDs
    if "material_id" in required_params and isinstance(material_ids, list) and len(material_ids) > 1:
        by_material: Dict[str, Any] = {}
        errors: Dict[str, Any] = {}
        for material_id in material_ids:
            single = dict(params)
            single.pop("material_ids", None)
            single["material_id"] = material_id
            one = await invoke_once(single)
            if "error" in one:
                errors[material_id] = one["error"]
            else:
                by_material[material_id] = one.get("result")

        if errors and not by_material:
            return {"skill_id": skill_id, "error": json.dumps(errors)}

        result_payload: Dict[str, Any] = {
            "materials": material_ids,
            "by_material": by_material,
        }
        if errors:
            result_payload["partial_errors"] = errors
        return {"skill_id": skill_id, "result": result_payload}

    one = await invoke_once(params)
    if "input_required" in one:
        return {
            "skill_id": skill_id,
            "input_required": one["input_required"],
            "_a2a_context_id": one.get("_a2a_context_id"),
            "_a2a_task_id": one.get("_a2a_task_id"),
        }
    if "error" in one:
        item = {"skill_id": skill_id, "error": one["error"]}
        if one.get("missing_required_params"):
            item["missing_required_params"] = one["missing_required_params"]
        return item
    return {"skill_id": skill_id, "result": one.get("result")}


def _unique_workflow_skills(workflow) -> List[str]:
    skills: List[str] = []
    for step in workflow.definition.steps:
        if step.skill_id and step.skill_id not in skills:
            skills.append(step.skill_id)
    return skills


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
    conversation_id = state.get("conversation_id")
    store_status_update(
        conversation_id,
        "Planning request: matching workflows and selecting capabilities.",
    )

    cache = get_capability_cache()
    capabilities = await cache.get_capabilities()
    capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}
    seed_params = dict(seed_params or {})

    workflow_registry = get_workflow_registry() if ENABLE_WORKFLOW_LIBRARY else None
    matched_workflow = None
    workflow_candidates: List[WorkflowPlanningCandidate] = []
    if workflow_registry is not None:
        if explicit_workflow_id:
            selected = workflow_registry.get(explicit_workflow_id, version=explicit_workflow_version)
            if selected:
                matched_workflow = selected
                workflow_candidates.append(
                    WorkflowPlanningCandidate(
                        workflow_id=selected.definition.id,
                        workflow_version=selected.definition.version,
                        score=1.0,
                        required_paths=list(selected.required_input_paths),
                        selection_source=selection_source or "catalog",
                        skills=_unique_workflow_skills(selected),
                        execution_mode=selected.definition.execution.mode,
                        estimated_duration_seconds=selected.definition.metadata.estimated_duration_seconds,
                        display_name=selected.definition.ui.display_name or selected.definition.name,
                        summary=selected.definition.ui.summary or selected.definition.description,
                        extracted_params=seed_params,
                    )
                )
        else:
            matches = match_workflows(query=query, workflows=workflow_registry.list_all())
            for item in matches[:5]:
                workflow = workflow_registry.get(item.workflow_id, version=item.workflow_version)
                if not workflow:
                    continue
                workflow_candidates.append(
                    WorkflowPlanningCandidate(
                        workflow_id=workflow.definition.id,
                        workflow_version=workflow.definition.version,
                        score=item.score,
                        required_paths=list(workflow.required_input_paths),
                        selection_source="matcher",
                        skills=_unique_workflow_skills(workflow),
                        execution_mode=workflow.definition.execution.mode,
                        estimated_duration_seconds=workflow.definition.metadata.estimated_duration_seconds,
                        display_name=workflow.definition.ui.display_name or workflow.definition.name,
                        summary=workflow.definition.ui.summary or workflow.definition.description,
                        extracted_params=dict(item.extracted_params),
                    )
                )
            if workflow_candidates:
                top = workflow_candidates[0]
                matched_workflow = workflow_registry.get(top.workflow_id, version=top.workflow_version)

    # Catalog-selected workflows bypass matcher/router selection and resolve requirements directly.
    if explicit_workflow_id and matched_workflow is not None:
        store_status_update(
            conversation_id,
            f"Using selected workflow template '{matched_workflow.definition.id}'.",
        )
        selected_skills = _unique_workflow_skills(matched_workflow)
        extracted_params = enrich_material_params(query, seed_params)
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
            store_status_update(
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
            "reasoning": f"Catalog-selected workflow {matched_workflow.definition.id}",
            "agent_url": None,
            "requires_approval": requires_approval,
            "required_params": required_params,
            "missing_required_params": missing_required_params,
        }
        plan_steps = [
            f"Step {idx}: Invoke '{step.skill_id}' ({step.id})"
            for idx, step in enumerate(matched_workflow.definition.steps, 1)
        ]
        store_status_update(
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

    store_status_update(conversation_id, "Calling planner LLM for routing decision.")
    planning_result = await compile_plan_with_tools(
        query=query,
        capabilities=capabilities,
        history=conversation_history,
        context=context,
        workflow_candidates=workflow_candidates,
        forced_workflow_id=explicit_workflow_id,
        forced_workflow_version=explicit_workflow_version,
        forced_selection_source=selection_source,
        status_callback=lambda msg: store_status_update(conversation_id, msg),
    )

    if planning_result.outcome == "fallback" or not planning_result.primary_skill:
        # Guardrail: if deterministic workflow matching found candidates, prefer that
        # over conversational fallback so missing-parameter collection remains structured
        # (`needs_info` + followup form) instead of plain text.
        if workflow_candidates and workflow_registry is not None:
            top = workflow_candidates[0]
            selected = workflow_registry.get(top.workflow_id, version=top.workflow_version)
            if selected:
                planning_result = PlanningResult(
                    outcome="agent_plan",
                    message="I've prepared a workflow plan and need a few parameters to continue.",
                    workflow_id=top.workflow_id,
                    workflow_version=top.workflow_version,
                    workflow_match_score=top.score,
                    selection_source=top.selection_source,
                    primary_skill=top.skills[0] if top.skills else None,
                    supporting_skills=top.skills[1:] if len(top.skills) > 1 else [],
                    workflow_type="workflow_template",
                    confidence=0.9,
                    reasoning=(
                        f"Deterministically matched workflow template "
                        f"{top.workflow_id}@{top.workflow_version}."
                    ),
                    extracted_params=dict(top.extracted_params or {}),
                    steps=[],
                    estimated_duration_seconds=top.estimated_duration_seconds or 120,
                )
                store_status_update(
                    conversation_id,
                    (
                        f"Using deterministic workflow match "
                        f"'{top.workflow_id}@{top.workflow_version}'."
                    ),
                )
            else:
                message = planning_result.message or "I couldn't find a capability plan for that request."
                store_status_update(conversation_id, "No capability plan found for this request.", final=True)
                return {
                    "is_fallback": True,
                    "fallback_message": message,
                }
        else:
            message = planning_result.message or "I couldn't find a capability plan for that request."
            store_status_update(conversation_id, "No capability plan found for this request.", final=True)
            return {
                "is_fallback": True,
                "fallback_message": message,
            }

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
        store_status_update(
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
    for skill_id in selected_skills:
        cap = capabilities_by_skill.get(skill_id)
        if not cap:
            continue
        if selected_workflow is None:
            user_required_paths = extract_required_param_paths(cap.input_schema)
            all_required_paths = extract_required_param_paths(cap.input_schema, include_internal=True)
            required_params_set.update(user_required_paths)
            runtime_required_params_set.update(set(all_required_paths) - set(user_required_paths))
        if cap.requires_approval:
            requires_approval = True

    required_params = sorted(required_params_set)
    runtime_required_params = sorted(runtime_required_params_set)
    extracted_seed = dict(seed_params)
    if selected_workflow_candidate and selected_workflow_candidate.extracted_params:
        extracted_seed.update(selected_workflow_candidate.extracted_params)
    extracted_seed.update(planning_result.extracted_params)
    extracted_params = enrich_material_params(query, extracted_seed)
    extracted_params = await resolve_params_via_capability_metadata(
        query=query,
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
        store_status_update(
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
        store_status_update(
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
        "reasoning": planning_result.reasoning or planning_result.message or query,
        "agent_url": primary_capability.agent_url if primary_capability else None,
        "requires_approval": requires_approval,
        "required_params": required_params,
        "missing_required_params": missing_required_params,
    }
    if planning_result.workflow_type == "workflow_template" and planning_result.workflow_id:
        store_status_update(
            conversation_id,
            (
                f"Routing decision: templated workflow "
                f"'{planning_result.workflow_id}@{planning_result.workflow_version}'."
            ),
        )
    elif planning_result.workflow_type == "single":
        store_status_update(
            conversation_id,
            f"Routing decision: single capability '{routing_decision.get('primary_skill')}'.",
        )
    else:
        skill_list = ", ".join(selected_skills) if selected_skills else "(none)"
        store_status_update(
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
            "intent": planning_result.reasoning or planning_result.message or query,
            "workflow_type": planning_result.workflow_type,
            "workflow_id": planning_result.workflow_id,
            "workflow_version": planning_result.workflow_version,
            "skills": selected_skills,
            "required_params": required_params,
            "steps": steps,
            "missing_info": missing_required_params,
            "estimated_duration_seconds": estimated_duration,
            "param_metadata": param_metadata,
        },
        "missing_info": missing_required_params,
        "planner_message": planning_result.message,
    }


async def invoke_agent_generic(state: AgentState) -> Dict:
    """Generic agent invocation - calls any agent based on routing decision.

    This function implements fully dynamic agent invocation with support for
    different workflow types (single, parallel, sequential). The workflow type
    is determined by the routing decision based on capability metadata.

    Workflow types:
    - single: Invoke one skill
    - parallel: Invoke multiple skills concurrently
    - sequential: Invoke skills in order, passing results between them

    All invocation logic is generic and data-driven - there is no hardcoded
    knowledge of specific agents or skills.

    Args:
        state: Current workflow state with routing_decision

    Returns:
        State updates with tool_results and conversation_history
    """
    routing_decision = state.get("routing_decision", {})
    selected_skills = order_skills_for_workflow(routing_decision)
    params = routing_decision.get("extracted_params", {})
    workflow_type = routing_decision.get("workflow_type", "single")
    conversation_id = state.get("conversation_id", str(uuid.uuid4()))

    print(
        f"[DEBUG] invoke_agent_generic: workflow_type={workflow_type}, "
        f"skills={selected_skills}, params={params}"
    )
    store_status_update(
        conversation_id,
        f"Executing {len(selected_skills)} skill(s) with workflow mode '{workflow_type}'.",
    )

    if not selected_skills:
        store_status_update(conversation_id, "No skills selected for execution.", final=True)
        return {
            "conversation_history": state.get("conversation_history", []) + [{
                "role": "assistant",
                "content": "I couldn't determine which agent to invoke. Please try rephrasing your request.",
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }],
            "awaiting_approval": False
        }

    try:
        # Execute skills based on workflow type
        if workflow_type == "parallel" and len(selected_skills) > 1:
            # Parallel: invoke all skills concurrently
            invocation_results = await asyncio.gather(
                *[invoke_skill(skill_id, params, conversation_id) for skill_id in selected_skills]
            )
        elif workflow_type == "sequential" and len(selected_skills) > 1:
            # Sequential: invoke skills in order, passing results between them
            invocation_results = []
            previous_results: Dict[str, Any] = {}
            for skill_id in selected_skills:
                invoke_params = dict(params)
                if previous_results:
                    # Pass upstream results to downstream skills
                    invoke_params["upstream_results"] = previous_results
                item = await invoke_skill(skill_id, invoke_params, conversation_id)
                invocation_results.append(item)
                if "result" in item:
                    previous_results[skill_id] = item["result"]
        else:
            # Single: invoke skills one by one (no result passing)
            invocation_results = []
            for skill_id in selected_skills:
                invocation_results.append(await invoke_skill(skill_id, params, conversation_id))

        tool_results: Dict[str, Any] = {}
        response_lines = []
        has_errors = False
        missing_required_params: List[str] = []
        pending_subagent_request: Optional[Dict[str, Any]] = None

        def append_skill_line(skill: str, text: str, *, is_error: bool = False) -> None:
            """Render plain text for single-skill success, bracketed for multi/error cases."""
            if is_error or len(selected_skills) > 1:
                response_lines.append(f"[{skill}] {text}")
            else:
                response_lines.append(text)

        for item in invocation_results:
            skill_id = item["skill_id"]
            if item.get("input_required"):
                payload = item.get("input_required", {}) or {}
                missing_inputs = payload.get("missing_inputs", []) if isinstance(payload, dict) else []
                auto_resolved, unresolved = resolve_missing_inputs_from_state(
                    state,
                    missing_inputs,
                )
                if auto_resolved:
                    resumed = await invoke_skill(
                        skill_id,
                        {
                            **params,
                            "provided_inputs": auto_resolved,
                            "_a2a_context_id": item.get("_a2a_context_id"),
                            "_a2a_task_id": item.get("_a2a_task_id"),
                        },
                        conversation_id,
                        emit_status=False,
                    )
                    if resumed.get("input_required"):
                        payload = resumed.get("input_required", {}) or {}
                        missing_inputs = payload.get("missing_inputs", []) if isinstance(payload, dict) else []
                        _, unresolved = resolve_missing_inputs_from_state(state, missing_inputs)
                        if not unresolved:
                            unresolved = list(missing_inputs)
                        if unresolved:
                            pending_subagent_request = {
                                "skill_id": skill_id,
                                "a2a_context_id": resumed.get("_a2a_context_id"),
                                "a2a_task_id": resumed.get("_a2a_task_id"),
                                "missing_inputs": unresolved,
                                "hint": payload.get("hint"),
                            }
                            missing_required_params.extend(
                                [str(entry.get("name") or "") for entry in unresolved if entry.get("name")]
                            )
                            continue
                        item = resumed
                    else:
                        item = resumed
                else:
                    pending_subagent_request = {
                        "skill_id": skill_id,
                        "a2a_context_id": item.get("_a2a_context_id"),
                        "a2a_task_id": item.get("_a2a_task_id"),
                        "missing_inputs": unresolved,
                        "hint": payload.get("hint"),
                    }
                    missing_required_params.extend(
                        [str(entry.get("name") or "") for entry in unresolved if entry.get("name")]
                    )
                    continue
            if "error" in item:
                has_errors = True
                tool_results[skill_id] = {"error": item["error"]}
                if item.get("missing_required_params"):
                    tool_results[skill_id]["missing_required_params"] = item["missing_required_params"]
                    missing_required_params.extend(item["missing_required_params"])
                append_skill_line(skill_id, f"Error: {item['error']}", is_error=True)
            else:
                result_data = item.get("result", {})
                tool_results[skill_id] = result_data
                if isinstance(result_data, dict) and result_data.get("by_material"):
                    by_material = result_data.get("by_material", {})
                    compared = ", ".join(by_material.keys())
                    append_skill_line(skill_id, f"Retrieved results for: {compared}")
                    summary = build_comparison_summary(state.get("user_query", ""), by_material)
                    if summary:
                        response_lines.append(summary)
                    else:
                        append_skill_line(skill_id, extract_result_text(result_data))
                else:
                    append_skill_line(skill_id, extract_result_text(result_data))

        if missing_required_params:
            routing_decision = dict(state.get("routing_decision", {}) or {})
            unique_missing = sorted(set(missing_required_params))
            routing_decision["missing_required_params"] = unique_missing
            return {
                "routing_decision": routing_decision,
                "tool_results": tool_results,
                "missing_info": unique_missing,
                "pending_subagent_request": pending_subagent_request,
                "awaiting_approval": False,
            }

        response_type = "error" if has_errors else (
            f"agent_response_{selected_skills[0]}" if len(selected_skills) == 1 else "agent_response_multi_skill"
        )
        response_content = "\n\n".join(response_lines)
        suggested_queries = collect_suggested_queries(tool_results, limit=3)
        assistant_metadata = {"suggested_queries": suggested_queries} if suggested_queries else None

        history_entry = {
            "role": "assistant",
            "content": response_content,
            "type": response_type,
            "tool_results": tool_results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if assistant_metadata:
            history_entry["message_metadata"] = assistant_metadata

        response_payload = {
            "conversation_history": state.get("conversation_history", []) + [history_entry],
            "tool_results": tool_results,
            "awaiting_approval": False
        }
        if assistant_metadata:
            response_payload["message_metadata"] = assistant_metadata
        merged_context = dict(state.get("context", {}) or {})
        context_changed = False
        cache = get_capability_cache()
        for skill_id, result_data in tool_results.items():
            capability = await cache.get_capability_by_skill_id(skill_id)
            if not capability or not capability.provides:
                continue
            extracted_maps = extract_provided_context_maps(result_data, capability.provides)
            for context_key, entries in extracted_maps.items():
                before = get_nested_value(merged_context, context_key)
                merge_context_map(merged_context, context_key, entries)
                after = get_nested_value(merged_context, context_key)
                if before != after:
                    context_changed = True

        if context_changed:
            response_payload["context"] = merged_context

        return response_payload

    except Exception as e:
        print(f"[ERROR] invoke_agent_generic failed: {e}")
        import traceback
        traceback.print_exc()
        store_status_update(conversation_id, f"Execution failed: {e}", final=True)
        return {
            "conversation_history": state.get("conversation_history", []) + [{
                "role": "assistant",
                "content": f"I encountered an error while invoking the agent: {str(e)}",
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }],
            "awaiting_approval": False
        }


async def ask_followup_dynamic(state: AgentState) -> Dict:
    """Generate followup questions dynamically from capability's input_schema.

    This function implements fully dynamic followup question generation based on
    capability metadata. Instead of hardcoded questions for specific skills, it:

    1. Identifies missing required parameters from routing decision
    2. Looks up parameter schemas from agent cards
    3. Generates appropriate questions based on parameter types and descriptions

    This means adding a new skill with different parameters automatically works
    without any code changes - the questions are generated from the schema.

    Args:
        state: Current workflow state with routing_decision

    Returns:
        State updates with followup_questions in conversation_history
    """
    pending_subagent = state.get("pending_subagent_request")
    if pending_subagent:
        questions = _questions_from_pending_subagent_request(state)
        return {
            "conversation_history": state.get("conversation_history", []) + [{
                "role": "assistant",
                "type": "followup_questions",
                "questions": questions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
            "missing_info": [str(q.get("field") or "") for q in questions if q.get("field")],
            "awaiting_approval": False,
        }

    routing_decision = state.get("routing_decision", {})
    required_params = await resolve_user_required_params(routing_decision)
    provided_params = routing_decision.get("extracted_params", {}) or {}
    missing_params = [param for param in required_params if not has_param_path(provided_params, param)]
    if not missing_params:
        missing_params = routing_decision.get("missing_required_params", [])
    routing_decision["required_params"] = required_params
    routing_decision["missing_required_params"] = missing_params
    state["routing_decision"] = routing_decision
    selected_skills = get_selected_skills(routing_decision)

    print(f"[DEBUG] ask_followup_dynamic: skills={selected_skills}, missing_params={missing_params}")

    if not missing_params:
        return {
            "conversation_history": state.get("conversation_history", []),
            "awaiting_approval": False
        }

    # Gather parameter schemas from all selected skills
    cache = get_capability_cache()
    properties: Dict[str, Any] = {}
    for skill_id in selected_skills:
        capability = await cache.get_capability_by_skill_id(skill_id)
        if capability:
            properties.update(flatten_schema_properties(capability.input_schema))

    # Fallback to primary capability only if selected_skills metadata is unavailable
    if not properties and routing_decision.get("primary_skill"):
        capability = await cache.get_capability_by_skill_id(routing_decision["primary_skill"])
        if capability:
            properties = flatten_schema_properties(capability.input_schema)

    questions = []

    for param in missing_params:
        prop_info = properties.get(param, {})
        if not prop_info and "." in param:
            prop_info = properties.get(param.split(".", 1)[1], {})
        param_type = prop_info.get("type", "string")
        param_desc = prop_info.get("description", "")
        param_enum = prop_info.get("enum", [])
        param_display = param.replace(".", " ").replace("_", " ")

        if param == "question" or param == "query":
            questions.append({
                "field": param,
                "question": param_desc or "What would you like to know?",
                "type": "text"
            })
        elif param_type == "number" or param_type == "integer":
            questions.append({
                "field": param,
                "question": param_desc or f"Please provide the {param_display}:",
                "type": "number"
            })
        elif param_enum:
            questions.append({
                "field": param,
                "question": param_desc or f"Please select {param_display}:",
                "type": "select",
                "options": param_enum
            })
        else:
            questions.append({
                "field": param,
                "question": param_desc or f"Please provide {param_display}:",
                "type": "text"
            })

    return {
        "conversation_history": state.get("conversation_history", []) + [{
            "role": "assistant",
            "type": "followup_questions",
            "questions": questions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }],
        "missing_info": missing_params,  # For backward compatibility
        "awaiting_approval": False
    }


async def extract_followup_answers_from_query(state: AgentState, query: str) -> Dict[str, Any]:
    """Extract missing required parameters from a natural-language followup response.

    Uses selected capability schemas and current missing params from routing_decision.
    """
    routing_decision = state.get("routing_decision", {}) or {}
    required_params = await resolve_user_required_params(routing_decision)
    provided_params = routing_decision.get("extracted_params", {}) or {}
    missing_params = [param for param in required_params if not has_param_path(provided_params, param)]
    if not missing_params:
        missing_params = routing_decision.get("missing_required_params", []) or state.get("missing_info", [])
    if not missing_params:
        return {}

    selected_skills = get_selected_skills(routing_decision)
    cache = get_capability_cache()
    properties: Dict[str, Any] = {}
    for skill_id in selected_skills:
        capability = await cache.get_capability_by_skill_id(skill_id)
        if capability:
            properties.update(flatten_schema_properties(capability.input_schema))

    param_schema = {param: properties.get(param, {"type": "string"}) for param in missing_params}

    prompt = f"""Extract parameter values from the user's followup response.

USER FOLLOWUP RESPONSE:
{query}

PARAMETERS TO EXTRACT (JSON schema by field):
{json.dumps(param_schema, indent=2)}

REQUIRED OUTPUT KEYS:
{json.dumps(missing_params)}

Rules:
- Return ONLY a JSON object.
- Include only keys from REQUIRED OUTPUT KEYS.
- Only extract values that are explicitly stated in the user's text.
- Never infer defaults, typical operating conditions, or domain assumptions.
- If a value is not present or is uncertain, set it to null.
- Preserve data types (number/integer/boolean/array/object/string) per schema when possible.
"""

    llm = create_llm()
    store_status_update(state.get("conversation_id"), "Calling planner LLM to extract follow-up answers.")
    response = await asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)])
    parsed = extract_json_from_text(response.content)
    if not isinstance(parsed, dict):
        return {}

    extracted: Dict[str, Any] = {}
    for param in missing_params:
        value = get_nested_value(parsed, param)
        if value is None or value == "":
            continue
        if param == "material_id":
            inferred = extract_material_ids_from_text(str(value))
            if inferred:
                extracted["material_id"] = inferred[0]
                if len(inferred) > 1:
                    extracted["material_ids"] = inferred
                continue
        extracted[param] = value

    # Fallback: infer material IDs directly from the user followup text.
    if "material_id" in missing_params and "material_id" not in extracted:
        inferred = extract_material_ids_from_text(query)
        if inferred:
            extracted["material_id"] = inferred[0]
            if len(inferred) > 1:
                extracted["material_ids"] = inferred

    return extracted


async def apply_followup_answers_to_state(
    state: AgentState,
    followup_answers: Dict[str, Any],
    query: str = "",
) -> AgentState:
    """Merge follow-up answers into routing params and recompute missing requirements."""
    routing_decision = state.get("routing_decision", {}) or {}
    if not routing_decision:
        return state

    extracted_params = dict(routing_decision.get("extracted_params", {}))
    for key, value in (followup_answers or {}).items():
        if key == "material_id":
            inferred = extract_material_ids_from_text(str(value))
            if inferred:
                extracted_params["material_id"] = inferred[0]
                extracted_params["material_ids"] = inferred
                continue
        extracted_params[key] = value

    effective_query = state.get("user_query", "") or query or ""
    extracted_params = enrich_material_params(effective_query, extracted_params)
    extracted_params = await resolve_params_via_capability_metadata(
        query=effective_query,
        extracted_params=extracted_params,
        selected_skills=get_selected_skills(routing_decision),
        context=state.get("context", {}),
        conversation_history=state.get("conversation_history", []),
    )

    routing_decision["extracted_params"] = extracted_params
    required_params = await resolve_user_required_params(routing_decision)
    routing_decision["required_params"] = required_params
    routing_decision["missing_required_params"] = [
        param for param in required_params if not has_param_path(extracted_params, param)
    ]
    state["routing_decision"] = routing_decision
    state["missing_info"] = routing_decision["missing_required_params"]

    if extracted_params.get("material_id"):
        state["material_id"] = extracted_params.get("material_id")
    merged_context = dict(state.get("context", {}) or {})
    if isinstance(extracted_params.get("context"), dict):
        merged_context.update(extracted_params["context"])
    for key, value in extracted_params.items():
        if key.startswith("context.") and value is not None:
            merged_context[key.split(".", 1)[1]] = value
    if merged_context:
        state["context"] = merged_context

    return state


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
    cache = get_capability_cache()
    properties: Dict[str, Any] = {}
    for skill_id in selected_skills:
        capability = await cache.get_capability_by_skill_id(skill_id)
        if capability:
            properties.update(flatten_schema_properties(capability.input_schema))

    candidate_paths: List[str] = []
    workflow_type = routing_decision.get("workflow_type")
    workflow_id = routing_decision.get("workflow_id")
    workflow_version = routing_decision.get("workflow_version")
    if workflow_type == "workflow_template" and workflow_id and ENABLE_WORKFLOW_LIBRARY:
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
    prompt = f"""Extract parameter updates from this plan-refinement instruction.

REFINEMENT INSTRUCTION:
{text}

RECENT CONVERSATION:
{history_block}

CURRENT PARAMS:
{json.dumps(current_params, indent=2, default=str)}

ALLOWED PARAM KEYS (use these exact dotted keys):
{json.dumps(normalized_paths, indent=2)}

PARAM SCHEMA BY KEY:
{json.dumps(param_schema, indent=2, default=str)}

Rules:
- Return ONLY a JSON object.
- Include ONLY keys that should be updated by this refinement.
- Do NOT repeat unchanged values.
- If no updates are implied, return {{}}.
- Preserve schema data types when possible.
- If a duration field is in hours and user gives years/months/days, convert to hours.
"""

    llm = create_llm()
    response = await asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)])
    parsed = extract_json_from_text(response.content)
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
        missing = [param for param in required_params if not has_param_path(provided_params, param)]
        if not missing:
            missing = routing_decision.get("missing_required_params", []) or state.get("missing_info", [])

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
    missing = [param for param in required_params if not has_param_path(provided_params, param)]
    if not missing:
        missing = routing_decision.get("missing_required_params", []) or state.get("missing_info", [])

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


async def execute_current_plan(state: AgentState, *, start_message: str) -> AgentState:
    """Execute the current routing decision through the canonical execution path."""
    conversation_id = state.get("conversation_id", str(uuid.uuid4()))
    store_status_update(conversation_id, start_message)

    routing_decision = state.get("routing_decision", {}) or {}
    workflow_type = routing_decision.get("workflow_type", "single")
    workflow_final_output: Any = None

    if workflow_type == "workflow_template" and ENABLE_WORKFLOW_LIBRARY:
        workflow_id = routing_decision.get("workflow_id")
        workflow_version = routing_decision.get("workflow_version")
        registry = get_workflow_registry()
        compiled_workflow = registry.get(str(workflow_id or ""), version=workflow_version)
        if not compiled_workflow:
            raise RuntimeError(
                f"Workflow template '{workflow_id}'"
                f"{'@' + str(workflow_version) if workflow_version else ''} is unavailable."
            )
        store_status_update(
            conversation_id,
            (
                f"Executing workflow template "
                f"'{compiled_workflow.definition.id}@{compiled_workflow.definition.version}' "
                f"({len(compiled_workflow.definition.steps)} steps)."
            ),
        )

        input_params = dict(routing_decision.get("extracted_params", {}) or {})
        context_state = dict(state.get("context", {}) or {})
        execution_result = await execute_workflow(
            workflow=compiled_workflow,
            input_params=input_params,
            context=context_state,
            invoke_skill=invoke_skill,
            conversation_id=state.get("conversation_id", str(uuid.uuid4())) or str(uuid.uuid4()),
        )
        workflow_final_output = execution_result.get("final_output")
        step_statuses = execution_result.get("step_statuses", {}) or {}
        succeeded = [sid for sid, status in step_statuses.items() if status == "succeeded"]
        failed = [sid for sid, status in step_statuses.items() if status == "failed"]
        blocked = [sid for sid, status in step_statuses.items() if status == "blocked"]
        if succeeded:
            store_status_update(conversation_id, f"Completed workflow steps: {', '.join(succeeded)}.")
        if failed:
            store_status_update(conversation_id, f"Failed workflow steps: {', '.join(failed)}.")
        if blocked:
            store_status_update(conversation_id, f"Blocked workflow steps: {', '.join(blocked)}.")

        tool_results: Dict[str, Any] = {"workflow_execution": execution_result}
        for step_id, payload in (execution_result.get("step_results", {}) or {}).items():
            if not isinstance(payload, dict):
                continue
            skill_id = payload.get("skill_id") or step_id
            result = payload.get("result")
            tool_results[str(skill_id)] = result

        state["tool_results"] = tool_results
        if context_state:
            state["context"] = context_state
    else:
        invoke_update = await invoke_agent_generic(state)
        for key, value in invoke_update.items():
            if value is not None:
                state[key] = value
        if state.get("missing_info"):
            store_status_update(
                conversation_id,
                "Additional parameters are required before execution can continue.",
            )
            return state

    if workflow_type == "workflow_template":
        if workflow_final_output is None:
            raise RuntimeError(
                "Workflow completed without final output. Ensure the template defines a final synthesis step."
            )
        if isinstance(workflow_final_output, dict):
            summary = str(workflow_final_output.get("executive_summary") or "").strip()
            findings = workflow_final_output.get("key_findings")
            if summary and isinstance(findings, list) and findings:
                finding_lines = [f"- {str(item)}" for item in findings[:6]]
                final_report = f"{summary}\n\nKey findings:\n" + "\n".join(finding_lines)
            elif summary:
                final_report = summary
            else:
                final_report = extract_result_text(workflow_final_output)
        else:
            final_report = extract_result_text(workflow_final_output)
    else:
        # Non-template approvals return the combined direct invocation response.
        latest_history = state.get("conversation_history", []) or []
        latest_message = latest_history[-1].get("content") if latest_history else None
        final_report = str(latest_message or "").strip() or extract_result_text(state.get("tool_results", {}))
    state["final_report"] = final_report

    state["conversation_history"] = state.get("conversation_history", []) + [{
        "role": "assistant",
        "content": final_report,
        "type": "final_report",
        "tool_results": state.get("tool_results", {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]

    store_status_update(conversation_id, "Execution complete.", final=True)

    return state


async def execute_approved_plan(state: AgentState) -> AgentState:
    """Execute an approved plan using the same execution path as auto-execution."""
    return await execute_current_plan(state, start_message="Plan approved. Starting execution.")


async def refresh_discovery():
    """Manually refresh dynamic discovery artifacts without restarting the service."""
    result = await refresh_dynamic_components(trigger="api")
    return result


def _format_plan_for_response(state: AgentState) -> Dict[str, Any]:
    """Normalize internal plan state for frontend consumption."""
    plan = state.get("plan", {}) or {}
    routing_decision = state.get("routing_decision", {}) or {}
    return {
        "intent": plan.get("intent", "Capability execution"),
        "steps": plan.get("steps", []),
        "skills": plan.get("skills", []),
        "workflow_type": plan.get("workflow_type", "single"),
        "workflow_id": plan.get("workflow_id") or routing_decision.get("workflow_id"),
        "workflow_version": plan.get("workflow_version") or routing_decision.get("workflow_version"),
        "workflow_match_score": routing_decision.get("workflow_match_score"),
        "selection_source": routing_decision.get("selection_source"),
        "required_params": plan.get("required_params", []),
        "estimated_duration_seconds": plan.get("estimated_duration_seconds", 120),
        "material_id": state.get("material_id"),
        "analysis_types": state.get("analysis_types", []),
        "context": state.get("context", {}),
        "param_metadata": plan.get("param_metadata", {}),
    }


def _latest_conversation_entry(state: AgentState) -> Dict[str, Any]:
    """Return the latest conversation entry with safe fallback."""
    history = state.get("conversation_history", []) or []
    if history:
        return history[-1]
    return {}


def _coerce_followup_value(value: Any, value_type: str) -> Any:
    """Coerce form-submitted values into the type requested by a subagent."""
    if value is None:
        return None
    normalized_type = str(value_type or "").strip().lower()
    if normalized_type in {"number", "float"}:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if normalized_type == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if normalized_type == "boolean":
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    return value


def _lookup_context_value(state: AgentState, name: str) -> Any:
    """Resolve one missing-input name from orchestration state/context."""
    routing_decision = state.get("routing_decision", {}) or {}
    extracted_params = routing_decision.get("extracted_params", {}) or {}
    if name in extracted_params:
        return extracted_params.get(name)
    if isinstance(extracted_params.get("context"), dict) and name in extracted_params["context"]:
        return extracted_params["context"].get(name)
    context = state.get("context", {}) or {}
    if name in context:
        return context.get(name)
    if has_param_path(extracted_params, f"context.{name}"):
        return get_nested_value(extracted_params, f"context.{name}")
    if has_param_path(context, name):
        return get_nested_value(context, name)
    return None


def resolve_missing_inputs_from_state(
    state: AgentState,
    missing_inputs: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Resolve context-backed missing inputs using the orchestrator's shared state."""
    auto_resolved: Dict[str, Any] = {}
    unresolved: List[Dict[str, Any]] = []
    for item in missing_inputs or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if item.get("resolvable_from_context"):
            value = _lookup_context_value(state, name)
            if value is not None:
                auto_resolved[name] = value
                continue
        unresolved.append(item)
    return auto_resolved, unresolved


def _questions_from_pending_subagent_request(state: AgentState) -> List[Dict[str, Any]]:
    """Translate a pending INPUT_REQUIRED payload into frontend form fields."""
    pending = state.get("pending_subagent_request") or {}
    questions: List[Dict[str, Any]] = []
    for item in pending.get("missing_inputs", []) or []:
        input_type = str(item.get("type") or "string").strip().lower()
        questions.append(
            {
                "field": item.get("name"),
                "question": item.get("user_prompt") or item.get("description") or item.get("name"),
                "type": "number" if input_type in {"number", "integer"} else ("checkbox" if input_type == "boolean" else ("select" if input_type == "enum" else "text")),
                "options": item.get("options"),
                "description": item.get("description"),
                "required": True,
                "sensitive": bool(item.get("sensitive")),
                "value_type": input_type,
            }
        )
    return questions


async def resume_pending_subagent_request(
    state: AgentState,
    followup_answers: Dict[str, Any],
) -> AgentState:
    """Resume a previously blocked subagent task with user-provided inputs."""
    pending = dict(state.get("pending_subagent_request") or {})
    if not pending:
        return state

    skill_id = str(pending.get("skill_id") or "")
    routing_decision = dict(state.get("routing_decision", {}) or {})
    base_params = dict(routing_decision.get("extracted_params", {}) or {})
    typed_answers: Dict[str, Any] = {}
    for item in pending.get("missing_inputs", []) or []:
        name = str(item.get("name") or "").strip()
        if not name or name not in followup_answers:
            continue
        typed_answers[name] = _coerce_followup_value(followup_answers[name], str(item.get("type") or "string"))

    auto_resolved, _ = resolve_missing_inputs_from_state(state, pending.get("missing_inputs", []) or [])
    provided_inputs = {**auto_resolved, **typed_answers}

    resumed = await invoke_skill(
        skill_id,
        {
            **base_params,
            "provided_inputs": provided_inputs,
            "_a2a_context_id": pending.get("a2a_context_id"),
            "_a2a_task_id": pending.get("a2a_task_id"),
        },
        state.get("conversation_id", str(uuid.uuid4())) or str(uuid.uuid4()),
    )

    merged_context = dict(state.get("context", {}) or {})
    for item in pending.get("missing_inputs", []) or []:
        name = str(item.get("name") or "").strip()
        if not name or item.get("sensitive"):
            continue
        if name in provided_inputs:
            merged_context[name] = provided_inputs[name]
    state["context"] = merged_context

    if resumed.get("input_required"):
        payload = resumed.get("input_required", {}) or {}
        _, unresolved = resolve_missing_inputs_from_state(state, payload.get("missing_inputs", []) or [])
        state["pending_subagent_request"] = {
            "skill_id": skill_id,
            "a2a_context_id": resumed.get("_a2a_context_id"),
            "a2a_task_id": resumed.get("_a2a_task_id"),
            "missing_inputs": unresolved,
            "hint": payload.get("hint"),
        }
        state["missing_info"] = [str(item.get("name") or "") for item in unresolved if item.get("name")]
        return state

    state["pending_subagent_request"] = None
    state["missing_info"] = []

    if resumed.get("error"):
        state["tool_results"] = {skill_id: {"error": resumed["error"]}}
        state["final_report"] = f"[{skill_id}] Error: {resumed['error']}"
    else:
        result_data = resumed.get("result", {})
        state["tool_results"] = {skill_id: result_data}
        state["final_report"] = extract_result_text(result_data)

    state["conversation_history"] = state.get("conversation_history", []) + [{
        "role": "assistant",
        "content": state.get("final_report", ""),
        "type": f"agent_response_{skill_id}" if not resumed.get("error") else "error",
        "tool_results": state.get("tool_results", {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]
    return state


async def chat(request: ConversationRequest) -> ConversationResponse:
    """Conversational interface for material analysis."""
    conv_id = request.conversation_id or str(uuid.uuid4())
    store_status_update(conv_id, "Received request.")
    request_artifacts = summarize_artifacts_for_context(request.artifacts)
    existing_state = get_conversation(conv_id)
    has_pending_followup = bool(existing_state and existing_state.get("missing_info"))
    is_new_query_on_existing = (
        bool(existing_state)
        and bool(request.query)
        and not request.followup_answers
        and not request.plan_approved
        and not has_pending_followup
    )

    # Existing conversation continuation path: followup answers and/or approval.
    if existing_state and not is_new_query_on_existing:
        state = existing_state
        if request_artifacts:
            state["context"] = merge_artifacts_into_context(state.get("context", {}), request_artifacts)

        if request.plan_approved:
            state["awaiting_approval"] = False
            try:
                final_state = await execute_approved_plan(state)
                if final_state.get("missing_info"):
                    followup_result = await ask_followup_dynamic(final_state)
                    for key, value in followup_result.items():
                        if value is not None:
                            final_state[key] = value
                    store_conversation(conv_id, final_state)
                    store_status_update(conv_id, "Awaiting additional parameters.", final=True)
                    latest = _latest_conversation_entry(final_state)
                    return ConversationResponse(
                        conversation_id=conv_id,
                        status="needs_info",
                        message=(final_state.get("pending_subagent_request") or {}).get("hint") or "I need some additional information to proceed:",
                        followup_questions=latest.get("questions", []),
                    )
                store_conversation(conv_id, final_state)

                response_data = {
                    "conversation_id": conv_id,
                    "status": "completed",
                    "report": final_state.get("final_report", ""),
                    "tool_results": final_state.get("tool_results", {}),
                }
                store_status_update(conv_id, "Execution response ready.", final=True)
                return ConversationResponse(**response_data)
            except Exception as exc:
                store_status_update(conv_id, f"Execution failed: {exc}", final=True)
                return ConversationResponse(
                    conversation_id=conv_id,
                    status="error",
                    message=f"Error during analysis: {exc}",
                )

        followup_answers = dict(request.followup_answers or {})

        if request.query and not followup_answers and has_pending_followup and not state.get("pending_subagent_request"):
            state["conversation_history"] = state.get("conversation_history", []) + [{
                "role": "user",
                "content": request.query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
            extracted = await extract_followup_answers_from_query(state, request.query)
            followup_answers.update(extracted)

        if followup_answers:
            routing_decision = state.get("routing_decision", {}) or {}
            requires_approval = routing_decision.get("requires_approval", False)

            try:
                if state.get("pending_subagent_request"):
                    state = await resume_pending_subagent_request(state, followup_answers)
                    if state.get("missing_info"):
                        followup_result = await ask_followup_dynamic(state)
                        for key, value in followup_result.items():
                            if value is not None:
                                state[key] = value
                        store_conversation(conv_id, state)
                        store_status_update(conv_id, "Awaiting additional parameters.", final=True)
                        latest = _latest_conversation_entry(state)
                        pending = state.get("pending_subagent_request") or {}
                        return ConversationResponse(
                            conversation_id=conv_id,
                            status="needs_info",
                            message=pending.get("hint") or "I need some additional information to proceed:",
                            followup_questions=latest.get("questions", []),
                        )
                    store_conversation(conv_id, state)
                    store_status_update(conv_id, "Response ready.", final=True)
                    return ConversationResponse(
                        conversation_id=conv_id,
                        status="completed",
                        message=state.get("final_report", ""),
                        report=state.get("final_report", ""),
                        tool_results=state.get("tool_results"),
                    )

                if routing_decision:
                    state = await apply_followup_answers_to_state(
                        state,
                        followup_answers,
                        query=request.query or "",
                    )
                    routing_decision = state.get("routing_decision", {}) or routing_decision

                if state.get("missing_info"):
                    followup_result = await ask_followup_dynamic(state)
                    for key, value in followup_result.items():
                        if value is not None:
                            state[key] = value
                    store_conversation(conv_id, state)
                    store_status_update(conv_id, "Awaiting additional parameters.", final=True)
                    latest = _latest_conversation_entry(state)
                    return ConversationResponse(
                        conversation_id=conv_id,
                        status="needs_info",
                        message=(state.get("pending_subagent_request") or {}).get("hint") or "I need some additional information to proceed:",
                        followup_questions=latest.get("questions", []),
                    )

                if not requires_approval:
                    store_status_update(conv_id, "All required parameters resolved. Executing skills.")
                    final_state = await execute_current_plan(
                        state,
                        start_message="All required parameters resolved. Starting execution.",
                    )
                    if final_state.get("missing_info"):
                        followup_result = await ask_followup_dynamic(final_state)
                        for key, value in followup_result.items():
                            if value is not None:
                                final_state[key] = value
                        store_conversation(conv_id, final_state)
                        store_status_update(conv_id, "Awaiting additional parameters.", final=True)
                        latest = _latest_conversation_entry(final_state)
                        return ConversationResponse(
                            conversation_id=conv_id,
                            status="needs_info",
                            message=(final_state.get("pending_subagent_request") or {}).get("hint") or "I need some additional information to proceed:",
                            followup_questions=latest.get("questions", []),
                        )
                    store_conversation(conv_id, final_state)
                    store_status_update(conv_id, "Response ready.", final=True)
                    return ConversationResponse(
                        conversation_id=conv_id,
                        status="completed",
                        message=final_state.get("final_report", ""),
                        report=final_state.get("final_report", ""),
                        tool_results=final_state.get("tool_results"),
                    )

                plan_result = plan_analysis(state)
                for key, value in plan_result.items():
                    if value is not None:
                        state[key] = value
                show_plan_result = show_plan(state)
                for key, value in show_plan_result.items():
                    if value is not None:
                        state[key] = value

                store_conversation(conv_id, state)
                store_status_update(conv_id, "Plan ready for approval.", final=True)
                return ConversationResponse(
                    conversation_id=conv_id,
                    status="plan_ready",
                    message="I've created an analysis plan. Please review and approve:",
                    plan=_format_plan_for_response(state),
                )
            except Exception as exc:
                store_status_update(conv_id, f"Follow-up processing failed: {exc}", final=True)
                return ConversationResponse(
                    conversation_id=conv_id,
                    status="error",
                    message=f"Error processing followup: {exc}",
                )

        if request.query and has_pending_followup:
            if state.get("pending_subagent_request"):
                followup_result = await ask_followup_dynamic(state)
                for key, value in followup_result.items():
                    if value is not None:
                        state[key] = value
                store_conversation(conv_id, state)
                store_status_update(conv_id, "Awaiting additional parameters.", final=True)
                latest = _latest_conversation_entry(state)
                pending = state.get("pending_subagent_request") or {}
                return ConversationResponse(
                    conversation_id=conv_id,
                    status="needs_info",
                    message=pending.get("hint") or "I still need a few details to proceed:",
                    followup_questions=latest.get("questions", []),
                )
            followup_result = await ask_followup_dynamic(state)
            for key, value in followup_result.items():
                if value is not None:
                    state[key] = value
            store_conversation(conv_id, state)
            store_status_update(conv_id, "Awaiting additional parameters.", final=True)
            latest = _latest_conversation_entry(state)
            return ConversationResponse(
                conversation_id=conv_id,
                status="needs_info",
                message="I still need a few details to proceed:",
                followup_questions=latest.get("questions", []),
            )

        store_status_update(conv_id, "No actionable follow-up input was provided.", final=True)
        return ConversationResponse(
            conversation_id=conv_id,
            status="error",
            message="No actionable followup input was provided.",
        )

    # New query path: new conversation or new query in existing conversation.
    if not request.query and not request.workflow_id:
        store_status_update(
            conv_id,
            "A query or explicit workflow selection is required for a new planning turn.",
            final=True,
        )
        return ConversationResponse(
            conversation_id=conv_id,
            status="error",
            message="A query or explicit workflow selection is required for a new planning turn.",
        )

    if is_new_query_on_existing:
        old_history = existing_state.get("conversation_history", [])
        previous_context = existing_state.get("context", {})
    else:
        old_history = []
        previous_context = {}

    forced_workflow_id = request.workflow_id
    forced_workflow_version = request.workflow_version
    forced_selection_source = request.selection_source
    seed_params: Dict[str, Any] = {}
    if isinstance(request.followup_answers, dict):
        seed_params.update(request.followup_answers)

    # Plan-refinement turns (while awaiting approval) should preserve the
    # selected template and previously extracted parameters.
    if is_new_query_on_existing and isinstance(existing_state, dict) and existing_state.get("awaiting_approval"):
        existing_routing = existing_state.get("routing_decision", {}) or {}
        existing_plan = existing_state.get("plan", {}) or {}

        if not forced_workflow_id:
            forced_workflow_id = (
                existing_plan.get("workflow_id")
                or existing_routing.get("workflow_id")
            )
        if not forced_workflow_version:
            forced_workflow_version = (
                existing_plan.get("workflow_version")
                or existing_routing.get("workflow_version")
            )
        if not forced_selection_source:
            forced_selection_source = (
                existing_routing.get("selection_source")
                or "plan_refinement"
            )

        existing_params = existing_routing.get("extracted_params")
        if isinstance(existing_params, dict):
            merged_seed = dict(existing_params)
            merged_seed.update(seed_params)
            seed_params = merged_seed

        if request.query:
            store_status_update(conv_id, "Applying refinement instructions to plan parameters.")
            refinement_updates = await extract_refinement_param_updates(
                query=request.query,
                routing_decision=existing_routing,
                conversation_history=old_history,
            )
            if refinement_updates:
                merged_seed = dict(seed_params)
                merged_seed.update(refinement_updates)
                seed_params = merged_seed
                store_status_update(conv_id, "Refinement parameters applied.")

    previous_context = merge_artifacts_into_context(previous_context, request_artifacts)

    state: AgentState = {
        "messages": [],
        "conversation_id": conv_id,
        "user_query": request.query or f"Start workflow {request.workflow_id}",
        "conversation_history": old_history + [{
            "role": "user",
            "content": request.query or f"Start workflow {request.workflow_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "routing_decision": None,
        "plan": None,
        "missing_info": [],
        "awaiting_approval": False,
        "pending_subagent_request": None,
        "material_id": None,
        "analysis_types": None,
        "context": previous_context,
        "question": None,
        "tool_results": {},
        "final_report": None,
    }

    if isinstance(request.followup_answers, dict) and request.followup_answers:
        merged_context = dict(state.get("context", {}) or {})
        for key, value in request.followup_answers.items():
            if key.startswith("context."):
                merged_context[key.split(".", 1)[1]] = value
            elif key != "material_id":
                merged_context[key] = value
        if merged_context:
            state["context"] = merged_context

    try:
        planning_update = await compile_query_plan(
            state,
            explicit_workflow_id=forced_workflow_id,
            explicit_workflow_version=forced_workflow_version,
            selection_source=forced_selection_source or ("catalog" if forced_workflow_id else None),
            seed_params=seed_params or None,
        )
        if planning_update.get("is_fallback"):
            fallback_message = planning_update.get("fallback_message", "I couldn't plan a capability invocation for that query.")
            state["conversation_history"] = state.get("conversation_history", []) + [{
                "role": "assistant",
                "content": fallback_message,
                "type": "fallback_response",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
            store_conversation(conv_id, state)
            store_status_update(conv_id, "Responded without subagent execution.", final=True)
            return ConversationResponse(
                conversation_id=conv_id,
                status="answer",
                message=fallback_message,
                response_text=fallback_message,
            )

        for key, value in planning_update.items():
            if key in {"is_fallback", "fallback_message", "planner_message"}:
                continue
            if value is not None:
                state[key] = value

        if state.get("missing_info"):
            followup_result = await ask_followup_dynamic(state)
            for key, value in followup_result.items():
                if value is not None:
                    state[key] = value
            store_conversation(conv_id, state)
            store_status_update(conv_id, "Awaiting additional parameters.", final=True)
            latest = _latest_conversation_entry(state)
            return ConversationResponse(
                conversation_id=conv_id,
                status="needs_info",
                message=(state.get("pending_subagent_request") or {}).get("hint") or "I need some additional information to proceed:",
                followup_questions=latest.get("questions", []),
            )

        routing_decision = state.get("routing_decision", {}) or {}
        requires_approval = routing_decision.get("requires_approval", False)

        if requires_approval:
            plan_result = plan_analysis(state)
            for key, value in plan_result.items():
                if value is not None:
                    state[key] = value
            show_plan_result = show_plan(state)
            for key, value in show_plan_result.items():
                if value is not None:
                    state[key] = value
            store_conversation(conv_id, state)
            store_status_update(conv_id, "Plan ready for approval.", final=True)
            return ConversationResponse(
                conversation_id=conv_id,
                status="plan_ready",
                message=planning_update.get("planner_message") or "I've created an analysis plan. Please review and approve:",
                plan=_format_plan_for_response(state),
            )

        store_status_update(conv_id, "All required parameters resolved. Executing skills.")
        final_state = await execute_current_plan(
            state,
            start_message="All required parameters resolved. Starting execution.",
        )
        if final_state.get("missing_info"):
            followup_result = await ask_followup_dynamic(final_state)
            for key, value in followup_result.items():
                if value is not None:
                    final_state[key] = value
            store_conversation(conv_id, final_state)
            store_status_update(conv_id, "Awaiting additional parameters.", final=True)
            latest = _latest_conversation_entry(final_state)
            return ConversationResponse(
                conversation_id=conv_id,
                status="needs_info",
                message=(final_state.get("pending_subagent_request") or {}).get("hint") or "I need some additional information to proceed:",
                followup_questions=latest.get("questions", []),
            )
        store_conversation(conv_id, final_state)
        store_status_update(conv_id, "Response ready.", final=True)
        return ConversationResponse(
            conversation_id=conv_id,
            status="completed",
            message=final_state.get("final_report", ""),
            report=final_state.get("final_report", ""),
            tool_results=final_state.get("tool_results"),
        )
    except Exception as exc:
        store_status_update(conv_id, f"Request failed: {exc}", final=True)
        return ConversationResponse(
            conversation_id=conv_id,
            status="error",
            message=f"Error processing request: {exc}",
        )


async def get_status(conversation_id: str):
    """
    Get the current status of an ongoing analysis.

    Used by the frontend to poll for status updates during long-running operations.
    """
    import redis
    import os

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        key = f"agent:status:{conversation_id}"
        status_data = redis_client.get(key)
        history_key = f"agent:status_history:{conversation_id}"
        history_raw = redis_client.lrange(history_key, 0, -1)
        history: List[Dict[str, Any]] = []
        for item in history_raw:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    history.append(parsed)
            except Exception:
                continue

        if status_data:
            print(f"[STATUS] Found status for {conversation_id}: {status_data[:100]}...")
            payload = json.loads(status_data)
            if history:
                payload["history"] = history
            return payload
        if history:
            latest = history[-1]
            latest["history"] = history
            return latest
        else:
            # Check if there are any status keys to help debug
            all_keys = redis_client.keys("agent:status:*")
            print(f"[STATUS] No status for {conversation_id}. Available keys: {all_keys[:5]}")
            return {"message": "No status available", "final": False}
    except Exception as e:
        print(f"[STATUS] Error: {e}")
        return {"message": f"Error fetching status: {e}", "final": False}


class OrchestratorAgent(PrometheusAgent):
    """A2A-native orchestrator using the shared PrometheusAgent base class."""

    def __init__(self):
        super().__init__(
            agent_name="Nuclear Analysis Client Agent",
            agent_card_path="agent_card.json",
        )

    async def _on_startup(self) -> None:
        """Initialize dynamic discovery state when the HTTP app starts."""
        global _refresh_task

        print("Client Agent starting up...")
        await refresh_dynamic_components(trigger="startup")

        if DISCOVERY_REFRESH_SECONDS > 0 and _refresh_task is None:
            _refresh_task = asyncio.create_task(discovery_refresh_loop())
            print(
                f"Background discovery refresh enabled "
                f"({DISCOVERY_REFRESH_SECONDS}s interval)"
            )

        print("Client Agent ready!")

    async def _on_shutdown(self) -> None:
        """Cleanup background refresh task on server shutdown."""
        global _refresh_task

        print("Client Agent shutting down...")
        if _refresh_task:
            _refresh_task.cancel()
            try:
                await _refresh_task
            except asyncio.CancelledError:
                pass
            _refresh_task = None

    async def _status_endpoint(self, request) -> JSONResponse:
        """Status polling endpoint."""
        conversation_id = request.path_params.get("conversation_id")
        payload = await get_status(conversation_id)
        return JSONResponse(payload)

    async def _refresh_endpoint(self, request) -> JSONResponse:
        """Manual refresh endpoint for capability/tool discovery."""
        payload = await refresh_discovery()
        return JSONResponse(payload)

    async def _workflow_catalog_endpoint(self, request: Request) -> JSONResponse:
        """Return workflow catalog cards for frontend workflow picker."""
        if not ENABLE_WORKFLOW_LIBRARY:
            return JSONResponse({"workflows": [], "enabled": False})
        registry = get_workflow_registry()
        return JSONResponse(
            {
                "enabled": True,
                "workflows": registry.get_catalog(),
                "errors": registry.snapshot.errors,
            }
        )

    async def _workflow_input_form_endpoint(self, request: Request) -> JSONResponse:
        """Return unresolved required inputs for a workflow template."""
        if not ENABLE_WORKFLOW_LIBRARY:
            return JSONResponse({"error": "Workflow library disabled"}, status_code=404)

        workflow_id = str(request.path_params.get("workflow_id") or "").strip()
        version = request.query_params.get("version")
        conversation_id = request.query_params.get("conversation_id")
        state = get_conversation(conversation_id) if conversation_id else None
        params = {}
        if isinstance(state, dict):
            params = dict((state.get("routing_decision") or {}).get("extracted_params", {}) or {})
        context = dict((state or {}).get("context", {}) or {})

        cache = get_capability_cache()
        capabilities = await cache.get_capabilities()
        capabilities_by_skill = {cap.skill_id: cap for cap in capabilities}

        registry = get_workflow_registry()
        try:
            payload = registry.build_input_form(
                workflow_id=workflow_id,
                version=version,
                capabilities_by_skill=capabilities_by_skill,
                params=params,
                context=context,
            )
        except KeyError:
            return JSONResponse({"error": f"Workflow '{workflow_id}' not found"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"error": f"Failed to build workflow form: {exc}"}, status_code=500)

        return JSONResponse(payload)

    async def _workflow_start_endpoint(self, request: Request) -> JSONResponse:
        """Start a workflow-based conversation turn from catalog selections."""
        if not ENABLE_WORKFLOW_LIBRARY:
            return JSONResponse({"error": "Workflow library disabled"}, status_code=404)

        workflow_id = str(request.path_params.get("workflow_id") or "").strip()
        body = await request.json()
        query = body.get("query") or f"Start workflow {workflow_id}"
        conversation_id = body.get("conversation_id")
        workflow_version = body.get("workflow_version")
        form_values = body.get("inputs") if isinstance(body.get("inputs"), dict) else None
        artifacts = body.get("artifacts") if isinstance(body.get("artifacts"), list) else None
        registry = get_workflow_registry()
        if not registry.get(workflow_id, version=workflow_version):
            return JSONResponse(
                {"error": f"Workflow '{workflow_id}' not found"},
                status_code=404,
            )

        chat_request = ConversationRequest(
            query=query,
            conversation_id=conversation_id,
            followup_answers=form_values,
            artifacts=artifacts,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            selection_source="catalog",
        )
        response = await chat(chat_request)
        return JSONResponse(response.model_dump(exclude_none=True))

    async def _forward_status_history(
        self,
        conversation_id: str,
        context: RequestContext,
        event_queue: EventQueue,
        started_at: datetime,
        stop_event: asyncio.Event,
    ) -> None:
        """Forward Redis-backed status history entries into this task's event stream."""
        if not conversation_id:
            return

        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        except Exception as exc:
            print(f"[WARN] Status forwarder unavailable: {exc}")
            return

        history_key = f"agent:status_history:{conversation_id}"
        next_index = 0

        while True:
            try:
                raw_entries = redis_client.lrange(history_key, next_index, -1)
                if raw_entries:
                    next_index += len(raw_entries)
                    for raw in raw_entries:
                        try:
                            entry = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(entry, dict):
                            continue
                        message = str(entry.get("message", "")).strip()
                        if not message:
                            continue
                        ts = entry.get("timestamp")
                        if ts:
                            try:
                                entry_time = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                                if entry_time.tzinfo is None:
                                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                                if entry_time < started_at:
                                    continue
                            except Exception:
                                pass
                        await self.send_status_update(
                            context=context,
                            event_queue=event_queue,
                            message=message,
                        )
            except Exception as exc:
                print(f"[WARN] Status forwarder loop error: {exc}")

            if stop_event.is_set():
                break
            await asyncio.sleep(0.4)

    def _collect_artifact_reference_payloads(self, payload: Any) -> List[Any]:
        """Recursively collect artifact payloads from tool responses.

        Used by `_execute` after `chat(...)` so orchestrator conversation state can
        track artifacts produced by downstream agents.
        """
        collected: List[Any] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if (
                    isinstance(node.get("parts"), list)
                    or node.get("uri")
                    or node.get("json_body") is not None
                ):
                    collected.append(node)
                artifact_node = node.get("artifact")
                if artifact_node is not None:
                    walk(artifact_node)
                artifacts_node = node.get("artifacts")
                if isinstance(artifacts_node, list):
                    for item in artifacts_node:
                        walk(item)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return collected

    def _ingest_response_artifacts(self, conversation_id: str, payload: Dict[str, Any]) -> int:
        """Register downstream artifact refs into this orchestrator conversation scope."""
        if not conversation_id:
            return 0

        ingested = 0
        for candidate in self._collect_artifact_reference_payloads(payload):
            try:
                reference = ArtifactReference.from_any(
                    candidate,
                    conversation_id=conversation_id,
                )
            except Exception:
                continue
            if reference is None or not reference.name:
                continue
            if not reference.uri and reference.json_body is None:
                continue
            metadata = dict(reference.metadata or {})
            if metadata.get("kind") == "conversation_message":
                continue
            if reference.name == "conversation_message":
                continue

            if reference.conversation_id and reference.conversation_id != conversation_id:
                metadata.setdefault("source_conversation_id", reference.conversation_id)
                reference.metadata = metadata
            reference.conversation_id = conversation_id

            try:
                self.artifact_registry.register(reference)
                ingested += 1
            except Exception as exc:
                print(f"[WARN] Failed to ingest artifact reference: {exc}")

        return ingested

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """A2A entry point mapped to conversational orchestrator behavior."""
        request_payload = dict(params or {})
        if "query" not in request_payload and isinstance(request_payload.get("message"), str):
            request_payload["query"] = request_payload["message"]
        if "conversation_id" not in request_payload:
            request_payload["conversation_id"] = (
                request_payload.get("context_id")
                or context.context_id
                or str(uuid.uuid4())
            )
        conversation_id = str(request_payload.get("conversation_id") or context.context_id or "")

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Processing orchestration request.",
        )
        store_status_update(conversation_id, "Processing orchestration request.")

        if _tools_cache is None:
            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Refreshing capability and workflow caches.",
            )
            store_status_update(conversation_id, "Refreshing capability and workflow caches.")
            await refresh_dynamic_components(trigger="lazy-init")
            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Capability refresh complete. Continuing request.",
            )
            store_status_update(conversation_id, "Capability refresh complete. Continuing request.")
        existing_artifacts = []
        try:
            existing_artifacts = [
                ref.to_dict() for ref in self.list_artifact_references(conversation_id, limit=50)
            ]
        except Exception as exc:
            print(f"[WARN] Failed to list artifacts for {conversation_id}: {exc}")
        if existing_artifacts:
            request_payload["artifacts"] = merge_artifact_catalogs(
                existing_artifacts,
                request_payload.get("artifacts") if isinstance(request_payload.get("artifacts"), list) else None,
            )

        request_started_at = datetime.now(timezone.utc)
        status_forwarder_stop = asyncio.Event()
        status_forwarder_task = asyncio.create_task(
            self._forward_status_history(
                conversation_id=conversation_id,
                context=context,
                event_queue=event_queue,
                started_at=request_started_at,
                stop_event=status_forwarder_stop,
            )
        )

        chat_request = ConversationRequest.model_validate(request_payload)
        try:
            response = await chat(chat_request)
        finally:
            status_forwarder_stop.set()
            try:
                await asyncio.wait_for(status_forwarder_task, timeout=1.0)
            except Exception:
                status_forwarder_task.cancel()
                try:
                    await status_forwarder_task
                except Exception:
                    pass
        response_payload = response.model_dump(exclude_none=True)
        # Snapshot existing artifact IDs before ingestion so we can diff afterward
        try:
            existing_ids = {
                ref.artifact_id
                for ref in self.list_artifact_references(conversation_id, limit=50)
            }
        except Exception:
            existing_ids = set()
        try:
            ingested = self._ingest_response_artifacts(conversation_id, response_payload)
            if ingested:
                print(f"[DEBUG] Ingested {ingested} artifact reference(s) for {conversation_id}")
        except Exception as exc:
            print(f"[WARN] Failed to ingest artifacts from response payload: {exc}")
        try:
            all_refs = [
                ref.to_dict() for ref in self.list_artifact_references(conversation_id, limit=50)
            ]
            response_payload["artifacts"] = all_refs
            # new_artifacts = refs that weren't present before ingestion
            response_payload["new_artifacts"] = [
                r for r in all_refs
                if (r.get("artifact_id") or r.get("id")) not in existing_ids
            ]
        except Exception as exc:
            print(f"[WARN] Failed to attach artifacts to response: {exc}")
        return response_payload

    def configure_app(self, app) -> None:
        """Add custom orchestrator endpoints and lifecycle hooks."""
        app.add_event_handler("startup", self._on_startup)
        app.add_event_handler("shutdown", self._on_shutdown)
        app.add_route("/status/{conversation_id}", self._status_endpoint, methods=["GET"])
        app.add_route("/discovery/refresh", self._refresh_endpoint, methods=["POST"])
        app.add_route("/workflows/catalog", self._workflow_catalog_endpoint, methods=["GET"])
        app.add_route("/workflows/{workflow_id}/input-form", self._workflow_input_form_endpoint, methods=["GET"])
        app.add_route("/workflows/{workflow_id}/start", self._workflow_start_endpoint, methods=["POST"])


if __name__ == "__main__":
    agent = OrchestratorAgent()
    agent.run(port=AGENT_PORT)
