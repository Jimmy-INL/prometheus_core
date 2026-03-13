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

logger = logging.getLogger(__name__)

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")
SELF_AGENT_ID = (os.getenv("AGENT_HOST") or "").strip()
SELF_AGENT_PORT = (os.getenv("AGENT_PORT") or "8000").strip()


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def is_self_agent(agent_id: str, agent_url: str) -> bool:
    """Return True when a discovered agent record points to this orchestrator."""
    normalized_id = (agent_id or "").strip()
    normalized_url = _normalize_url(agent_url)

    if SELF_AGENT_ID and normalized_id == SELF_AGENT_ID:
        return True

    self_urls = {
        _normalize_url(f"http://{SELF_AGENT_ID}:{SELF_AGENT_PORT}") if SELF_AGENT_ID else "",
        _normalize_url(f"http://localhost:{SELF_AGENT_PORT}"),
        _normalize_url(f"http://127.0.0.1:{SELF_AGENT_PORT}"),
    }
    self_urls.discard("")
    return normalized_url in self_urls


async def discover_agents() -> List[Dict[str, Any]]:
    """
    Query registry for all available agents.

    Returns:
        List of agent metadata dictionaries
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{REGISTRY_URL}/agents")
        response.raise_for_status()
        return response.json()["agents"]


async def get_agent_card(agent_id: str) -> Dict[str, Any]:
    """
    Get full agent card from registry.

    Args:
        agent_id: The agent ID to fetch

    Returns:
        Complete agent card dictionary with skills, inputSchemas, etc.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{REGISTRY_URL}/agents/{agent_id}/card")
        response.raise_for_status()
        return response.json()


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


def _looks_like_artifact_reference_payload(payload: Any) -> bool:
    """Return True for metadata-only artifact reference payload dicts."""
    if not isinstance(payload, dict):
        return False
    uri = str(payload.get("uri") or "").strip()
    name = str(payload.get("name") or "").strip()
    return bool(uri and name)


async def call_a2a_agent(agent_url: str, skill_id: str, **kwargs) -> Dict[str, Any]:
    """
    Call an A2A agent using JSON-RPC protocol.

    Implements the Agent-to-Agent (A2A) communication protocol for invoking
    remote agent skills. Uses JSON-RPC with blocking=True to wait for completion.

    The response extraction handles the A2A protocol wrapper structure which can vary:
    - Checks status.message.parts for final results
    - Falls back to artifacts.parts for structured responses
    - Scans history for last agent message with JSON result

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

    # Build headers with Bearer token authentication
    headers = {"Content-Type": "application/json"}
    agent_secret = os.getenv("AGENT_SECRET")
    if agent_secret:
        headers["Authorization"] = f"Bearer {agent_secret}"

    # Use longer timeout for research agents that may take minutes
    timeout_seconds = 900.0  # 15 minutes
    print(f"[A2A] Sending request (timeout: {timeout_seconds}s)...")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            response = await client.post(agent_url, json=message, headers=headers)
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

            # Check status.message first - this is where the final result appears
            status = a2a_result.get("status", {})
            status_message = status.get("message", {})
            if status_message:
                parts = status_message.get("parts", [])
                for part in parts:
                    if part.get("kind") == "text" or part.get("type") == "text":
                        text_content = part.get("text", "")
                        try:
                            parsed = json.loads(text_content)
                            if isinstance(parsed, dict) and ("status" in parsed or "answer" in parsed or "error" in parsed):
                                print(f"[A2A] Extracted final response from status.message: {str(parsed)[:200]}...")
                                return parsed
                        except json.JSONDecodeError as e:
                            logger.debug(f"Failed to parse status message as JSON: {e}")

            # Check for artifacts (where the actual response might be)
            artifacts = a2a_result.get("artifacts", [])
            if artifacts:
                print(f"[A2A] Found {len(artifacts)} artifacts")
                parsed_artifacts = []
                latest_artifact_reference = None
                for artifact in artifacts:
                    parts = artifact.get("parts", [])
                    for part in parts:
                        if part.get("kind") == "text" or part.get("type") == "text":
                            text_content = part.get("text", "")
                            try:
                                parsed = json.loads(text_content)
                                parsed_artifacts.append(parsed)
                                if isinstance(parsed, dict):
                                    artifact_payload = None
                                    if _looks_like_artifact_reference_payload(parsed):
                                        artifact_payload = parsed
                                    elif _looks_like_artifact_reference_payload(parsed.get("artifact")):
                                        artifact_payload = parsed.get("artifact")
                                    elif _looks_like_artifact_reference_payload(parsed.get("artifact_reference")):
                                        artifact_payload = parsed.get("artifact_reference")
                                    if artifact_payload is not None:
                                        latest_artifact_reference = artifact_payload
                            except json.JSONDecodeError as e:
                                logger.debug(f"Failed to parse artifact part as JSON: {e}")

                # Prefer a structured terminal payload if available, otherwise
                # return the newest parsed artifact (final chunk for most agents).
                terminal_keys = {
                    "status",
                    "message",
                    "response_text",
                    "answer",
                    "report",
                    "followup_questions",
                    "plan",
                }
                for parsed in reversed(parsed_artifacts):
                    if isinstance(parsed, dict) and any(key in parsed for key in terminal_keys):
                        if (
                            latest_artifact_reference
                            and "artifact" not in parsed
                            and "artifact_reference" not in parsed
                        ):
                            enriched = dict(parsed)
                            enriched["artifact"] = latest_artifact_reference
                            parsed = enriched
                        print(f"[A2A] Extracted terminal response from artifact: {str(parsed)[:200]}...")
                        return parsed
                if parsed_artifacts:
                    parsed = parsed_artifacts[-1]
                    print(f"[A2A] Extracted latest artifact payload: {str(parsed)[:200]}...")
                    return parsed

            # The response is in the history array - find the LAST agent message with JSON content
            history = a2a_result.get("history", [])
            print(f"[A2A] History has {len(history)} messages")

            # Iterate in reverse to find the last agent message with actual JSON result
            for msg in reversed(history):
                if msg.get("role") == "agent":
                    parts = msg.get("parts", [])
                    for part in parts:
                        if part.get("kind") == "text" or part.get("type") == "text":
                            text_content = part.get("text", "")
                            # Try to parse as JSON - look for responses with 'status' or 'answer' keys
                            try:
                                parsed = json.loads(text_content)
                                # Check if this looks like the actual result (not just a status message)
                                if isinstance(parsed, dict) and ("status" in parsed or "answer" in parsed or "error" in parsed):
                                    print(f"[A2A] Extracted final response: {str(parsed)[:200]}...")
                                    return parsed
                            except json.JSONDecodeError as e:
                                # Not JSON, continue looking
                                logger.debug(f"Failed to parse history message as JSON: {e}")

            # If no JSON result found, return the last text message
            for msg in reversed(history):
                if msg.get("role") == "agent":
                    parts = msg.get("parts", [])
                    for part in parts:
                        if part.get("kind") == "text" or part.get("type") == "text":
                            text_content = part.get("text", "")
                            print(f"[A2A] Returning last text message: {text_content[:100]}...")
                            return {"response": text_content}

            # Fallback: return the raw result
            print(f"[A2A] Could not extract response from history, returning raw result")
            return a2a_result
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
            agent_url = agent["url"]

            # Never expose this orchestrator's own skills as dynamic tools.
            # Otherwise the router can recursively invoke itself via A2A.
            if is_self_agent(agent_id, agent_url):
                print(f"Skipping self agent in tool discovery: {agent_id} ({agent_url})")
                continue

            # Get full agent card with skill details
            agent_card = await get_agent_card(agent_id)

            # Create one tool per skill
            for skill in agent_card.get("skills", []):
                tool = await create_tool_from_skill(agent_url, skill)
                tools.append(tool)
                print(f"Discovered tool: {skill['id']} from {agent_id}")
        except Exception as e:
            print(f"Warning: Failed to create tools for agent {agent_id}: {e}")
            continue

    print(f"Total tools discovered: {len(tools)}")
    return tools
