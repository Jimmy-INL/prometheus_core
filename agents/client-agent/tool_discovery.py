"""
Dynamic tool discovery from A2A registry.
Creates LangChain tools by discovering agents and their skills from the registry.
"""
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model
from prometheus_api.agent import ArtifactReference

logger = logging.getLogger(__name__)

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")
SELF_AGENT_ID = (os.getenv("AGENT_HOST") or "").strip()
SELF_AGENT_PORT = (os.getenv("AGENT_PORT") or "8000").strip()


def _litellm_headers() -> Dict[str, str]:
    headers = {}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"
    return headers


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def is_self_agent(agent_id: str, agent_url: str) -> bool:
    """Return True when a discovered agent record points to this orchestrator.

    agent_id here is the agent_name used in LiteLLM registration (e.g. 'client-agent'),
    which matches AGENT_HOST for the self-check.
    """
    if SELF_AGENT_ID and (agent_id or "").strip() == SELF_AGENT_ID:
        return True

    # Fallback: direct URL match for the agent's own address
    normalized_url = _normalize_url(agent_url)
    self_urls = {
        _normalize_url(f"http://{SELF_AGENT_ID}:{SELF_AGENT_PORT}") if SELF_AGENT_ID else "",
        _normalize_url(f"http://localhost:{SELF_AGENT_PORT}"),
        _normalize_url(f"http://127.0.0.1:{SELF_AGENT_PORT}"),
    }
    self_urls.discard("")
    return normalized_url in self_urls


async def discover_agents() -> List[Dict[str, Any]]:
    """Query LiteLLM for all registered A2A agents.

    Returns a normalised list where each entry contains:
      agent_id   – the agent_name used as LiteLLM routing key
      name       – human-readable name from agent_card_params
      url        – downstream agent base URL (from agent_card_params.url)
      agent_name – same as agent_id, kept for clarity
      agent_card_params – full card dict including skills + inputSchema
    """
    async with httpx.AsyncClient(timeout=10.0, headers=_litellm_headers()) as client:
        response = await client.get(f"{LITELLM_URL}/v1/agents")
        response.raise_for_status()
        raw = response.json()

    result = []
    # LiteLLM returns a list directly or wrapped in a key — handle both
    entries = raw if isinstance(raw, list) else raw.get("data", raw.get("agents", []))
    for entry in entries:
        card = entry.get("agent_card_params") or {}
        agent_name = entry.get("agent_name", "")
        result.append({
            "agent_id": agent_name,
            "agent_name": agent_name,
            "name": card.get("name", agent_name),
            "url": card.get("url", ""),
            "agent_card_params": card,
        })
    return result


async def get_agent_card(agent_id: str, direct_url: Optional[str] = None) -> Dict[str, Any]:
    """Get the full agent card for an agent.

    agent_id is the agent_name (LiteLLM routing key). Prefer the specialist's
    direct well-known agent-card endpoint because LiteLLM's `/a2a/{agent_name}`
    response drops non-standard per-skill metadata such as `inputSchema`.
    Falls back to LiteLLM and finally to the discovery summary payload.
    """
    normalized_direct_url = _normalize_url(direct_url or "")
    if normalized_direct_url:
        for path in ("/api/agent-card", "/.well-known/agent-card.json", "/.well-known/agent.json"):
            try:
                async with httpx.AsyncClient(timeout=10.0, headers=_litellm_headers()) as client:
                    response = await client.get(f"{normalized_direct_url}{path}")
                    if response.status_code == 200:
                        return response.json()
            except Exception:
                pass

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_litellm_headers()) as client:
            response = await client.get(f"{LITELLM_URL}/a2a/{agent_id}")
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass

    # Fallback: find the card in the full agent list
    agents = await discover_agents()
    for agent in agents:
        if agent["agent_id"] == agent_id:
            return agent.get("agent_card_params", {})
    return {}


def create_input_schema_from_skill(skill: Dict) -> type[BaseModel]:
    """
    Create Pydantic model from skill's inputSchema.

    Dynamically generates a Pydantic model class from a JSON schema definition
    in the agent card. This enables LangChain to validate tool inputs and provide
    proper type information to the LLM.

    Handles:
    - Simple schemas (single question parameter)
    - Complex schemas (multiple typed parameters)
    - Reserved field name conflicts (schema, model_fields, etc.)
    - Optional vs required parameters
    - Nested objects, arrays, enums

    Args:
        skill: Skill dictionary from agent card with optional "inputSchema" field

    Returns:
        Dynamically created Pydantic model class
    """
    # Reserved Pydantic v2 field names that conflict with BaseModel class attributes.
    # Note: "schema" is NOT reserved in Pydantic v2 (it was only in v1).
    RESERVED_NAMES = {"model_fields", "model_config", "model_computed_fields"}

    # Generic fallback schema when a skill does not define inputSchema.
    # Allow extra kwargs so drop-in skills can still be called.
    class DefaultGenericInput(BaseModel):
        conversation_id: Optional[str] = Field(
            default=None,
            description="Conversation ID for status tracking"
        )
        model_config = ConfigDict(extra="allow")

    # If no inputSchema provided, use default
    if "inputSchema" not in skill:
        return DefaultGenericInput

    input_schema = skill["inputSchema"]
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    # Build field definitions for dynamic model
    fields = {}
    for prop_name, prop_schema in properties.items():
        # Rename reserved field names to avoid Pydantic conflicts
        field_name = prop_name
        if prop_name in RESERVED_NAMES:
            field_name = f"{prop_name}_"

        # Determine field type from JSON schema type
        prop_type = prop_schema.get("type", "string")

        if prop_type == "object":
            field_type = Dict[str, Any]
        elif prop_type == "array":
            field_type = List[Any]
        elif prop_type == "integer":
            field_type = int
        elif prop_type == "number":
            field_type = float
        elif prop_type == "boolean":
            field_type = bool
        else:
            field_type = str

        # Build field metadata once. For optional fields we must provide the default
        # directly to Field(...); mutating FieldInfo.default later does not reliably
        # mark the field optional in dynamic create_model() schemas.
        field_kwargs = {
            "description": prop_schema.get("description", ""),
        }
        if prop_name in RESERVED_NAMES:
            # Preserve original JSON key when serializing/deserializing.
            field_kwargs["alias"] = prop_name

        if prop_name in required:
            fields[field_name] = (field_type, Field(**field_kwargs))
        else:
            default_value = prop_schema.get("default", None)
            fields[field_name] = (
                Optional[field_type],
                Field(default=default_value, **field_kwargs),
            )

    # Always add conversation_id for status tracking (not part of skill schema but needed for A2A)
    if "conversation_id" not in fields:
        fields["conversation_id"] = (
            Optional[str],
            Field(default=None, description="Conversation ID for status tracking")
        )

    # Create dynamic Pydantic model with populate_by_name for alias support
    model_name = f"{skill['id']}_input"

    # Allow extra fields for forward compatibility with evolving skill schemas.
    model = create_model(
        model_name,
        __config__=ConfigDict(populate_by_name=True, extra="allow"),
        **fields,
    )

    return model


def _normalize_a2a_artifacts(
    artifacts: Any,
    *,
    conversation_id: str,
) -> List[Dict[str, Any]]:
    """Normalize native A2A artifact payloads into catalog-entry dicts."""
    normalized: List[Dict[str, Any]] = []
    for artifact in artifacts or []:
        try:
            reference = ArtifactReference.from_any(
                artifact,
                conversation_id=conversation_id,
            )
        except Exception:
            reference = None
        if reference is None:
            continue
        if not reference.name:
            continue
        metadata = dict(reference.metadata or {})
        if metadata.get("kind") == "conversation_message":
            continue
        if reference.name == "conversation_message":
            continue
        normalized.append(reference.to_dict())
    return normalized


async def call_a2a_agent(agent_url: str, skill_id: str, **kwargs) -> Dict[str, Any]:
    """
    Call an A2A agent using JSON-RPC protocol.

    Implements the Agent-to-Agent (A2A) communication protocol for invoking
    remote agent skills. Uses JSON-RPC with blocking=True to wait for completion.

    The response extraction expects the canonical final response in
    result.status.message.parts[*].text and separately normalizes native
    A2A artifacts from result.artifacts.

    Args:
        agent_url: Base URL of the agent
        skill_id: The skill ID to invoke
        **kwargs: Parameters for the skill

    Returns:
        Agent's response (unwrapped from A2A protocol)
    """
    request_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    print(f"[A2A] Calling agent at {agent_url}")
    print(f"[A2A] Skill: {skill_id}, Params: {kwargs}")

    # Build A2A JSON-RPC message
    message = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": json.dumps(kwargs)
                    }
                ]
            },
            "configuration": {
                "blocking": True,  # Wait for task to complete before returning
            },
            "context": {
                "skillId": skill_id,
                "conversationId": kwargs.get("conversation_id", str(uuid.uuid4()))
            }
        }
    }

    # Route through LiteLLM: agent_url is {LITELLM_URL}/a2a/{agent_name}
    # LiteLLM's A2A endpoint requires the method in the URL path.
    endpoint = agent_url.rstrip("/") + "/message/send"
    headers = {"Content-Type": "application/json"}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"

    # Use longer timeout for research agents that may take minutes
    timeout_seconds = 900.0  # 15 minutes
    print(f"[A2A] Sending request (timeout: {timeout_seconds}s)...")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            response = await client.post(endpoint, json=message, headers=headers)
            print(f"[A2A] Response status: {response.status_code}")
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                print(f"[A2A] Agent returned error: {result['error']}")
                raise Exception(f"Agent error: {result['error']}")

            print(f"[A2A] Got result: {str(result)[:500]}...")

            # Extract the actual response from A2A protocol wrapper
            a2a_result = result.get("result", {})

            # Log full structure for debugging
            print(f"[A2A] Result keys: {list(a2a_result.keys())}")
            print(f"[A2A] Full result structure: {json.dumps(a2a_result, indent=2, default=str)[:2000]}")

            normalized_artifacts = _normalize_a2a_artifacts(
                a2a_result.get("artifacts", []),
                conversation_id=str(kwargs.get("conversation_id") or ""),
            )

            status = a2a_result.get("status", {})
            status_message = status.get("message", {})
            parts = status_message.get("parts", []) if isinstance(status_message, dict) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                root = part.get("root") if isinstance(part.get("root"), dict) else None
                part_kind = str(part.get("kind") or part.get("type") or (root or {}).get("kind") or "").strip().lower()
                if part_kind != "text":
                    continue
                text_content = part.get("text")
                if text_content is None and root is not None:
                    text_content = root.get("text", "")
                try:
                    parsed = json.loads(text_content)
                except json.JSONDecodeError as e:
                    logger.debug(f"Failed to parse final status message as JSON: {e}")
                    continue
                if not isinstance(parsed, dict):
                    continue
                if normalized_artifacts and "artifacts" not in parsed:
                    parsed = {**parsed, "artifacts": normalized_artifacts}
                print(f"[A2A] Extracted final response from status.message: {str(parsed)[:200]}...")
                return parsed

            error_payload: Dict[str, Any] = {
                "status": "error",
                "message": "Agent response missing canonical final status payload.",
            }
            if normalized_artifacts:
                error_payload["artifacts"] = normalized_artifacts
            return error_payload
        except httpx.TimeoutException as e:
            print(f"[A2A] Request timed out: {e}")
            raise Exception(f"Agent request timed out after {timeout_seconds}s")
        except httpx.HTTPStatusError as e:
            print(f"[A2A] HTTP error: {e}")
            raise
        except Exception as e:
            print(f"[A2A] Unexpected error: {e}")
            raise


async def create_tool_from_skill(
    agent_url: str,
    skill: Dict[str, Any]
) -> StructuredTool:
    """
    Create LangChain tool from agent skill definition.

    Uses skill metadata from agent card:
    - name becomes tool name
    - description becomes tool description
    - inputSchema becomes Pydantic model

    Args:
        agent_url: Base URL of the agent
        skill: Skill dictionary from agent card

    Returns:
        LangChain StructuredTool
    """
    skill_id = skill["id"]
    skill_name = skill.get("name", skill_id)
    skill_description = skill.get("description", "")

    # Build a map of renamed fields (field_name_ -> original_name) so we can
    # restore original JSON keys before forwarding params to the downstream agent.
    input_schema_def = skill.get("inputSchema", {})
    _reserved = {"model_fields", "model_config", "model_computed_fields"}
    _rename_map = {
        f"{name}_": name
        for name in (input_schema_def.get("properties", {}) or {})
        if name in _reserved
    }

    # Create async function to call the agent
    async def call_agent(**kwargs) -> str:
        try:
            # Remap any Pydantic-renamed fields back to their original names
            remapped = {_rename_map.get(k, k): v for k, v in kwargs.items()}
            result = await call_a2a_agent(agent_url, skill_id, **remapped)
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # Create input schema from skill definition
    input_schema = create_input_schema_from_skill(skill)

    return StructuredTool.from_function(
        coroutine=call_agent,
        name=skill_id,
        description=skill_description,
        args_schema=input_schema,
    )


async def get_all_tools_dynamic() -> List[StructuredTool]:
    """
    Discover all available agents and create tools dynamically.

    This replaces the hardcoded get_all_tools() function.
    Queries the registry for agents, fetches their agent cards,
    and creates LangChain tools from their skills.

    Returns:
        List of LangChain tools
    """
    try:
        agents = await discover_agents()
    except Exception as e:
        print(f"Warning: Failed to discover agents from registry: {e}")
        print("Falling back to empty tool list")
        return []

    tools = []

    for agent in agents:
        try:
            agent_id = agent["agent_id"]
            direct_url = agent["url"]   # downstream URL, used only for self-check

            # Never expose this orchestrator's own skills as dynamic tools.
            if is_self_agent(agent_id, direct_url):
                print(f"Skipping self agent in tool discovery: {agent_id} ({direct_url})")
                continue

            # Route all calls through LiteLLM rather than directly to the agent.
            litellm_url = f"{LITELLM_URL}/a2a/{agent_id}"

            # LiteLLM's /v1/agents payload can omit full per-skill metadata.
            # Fetch the full card so tool schemas stay authoritative.
            agent_card = await get_agent_card(agent_id, direct_url=direct_url)
            if not agent_card.get("skills"):
                agent_card = agent.get("agent_card_params") or agent_card

            # Create one tool per skill
            for skill in agent_card.get("skills", []):
                tool = await create_tool_from_skill(litellm_url, skill)
                tools.append(tool)
                print(f"Discovered tool: {skill['id']} from {agent_id}")
        except Exception as e:
            print(f"Warning: Failed to create tools for agent {agent_id}: {e}")
            continue

    print(f"Total tools discovered: {len(tools)}")
    return tools
