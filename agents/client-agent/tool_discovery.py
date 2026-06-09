"""
Dynamic tool discovery from A2A registry.
Creates LangChain tools by discovering agents and their skills from the registry.
"""
from collections.abc import Awaitable, Callable
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model
from prometheus_api.agent import ArtifactReference, PrometheusAgent

logger = logging.getLogger(__name__)

REGISTRY_URL = PrometheusAgent.registry_url()
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")
import socket as _socket

_AGENT_PORT = (os.getenv("AGENT_PORT") or "8000").strip()
SELF_AGENT_URL = (os.getenv("EXTERNAL_AGENT_URL") or f"http://{_socket.gethostname()}:{_AGENT_PORT}").rstrip("/")
# Docker Compose sets the container hostname to the service name; this is the
# agent_name key used when the client-agent registers with LiteLLM.
_SELF_AGENT_ID = _socket.gethostname()
StatusCallback = Callable[[str], Awaitable[None]]
# Invoked once when a downstream agent emits a status tagged metadata.background
# (declare_long_running). Receives the event metadata dict.
BackgroundCallback = Callable[[Dict[str, Any]], Awaitable[None]]


def _litellm_headers() -> Dict[str, str]:
    headers = {}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"
    return headers


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _extract_status_message_text(status_payload: Dict[str, Any]) -> str:
    """Extract plain text from a status.message payload."""
    message = status_payload.get("message", {}) if isinstance(status_payload, dict) else {}
    parts = message.get("parts", []) if isinstance(message, dict) else []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if str(part.get("kind") or "").strip().lower() == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _merge_a2a_artifacts(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge artifacts while preserving order and avoiding duplicates."""
    merged: List[Dict[str, Any]] = list(existing or [])
    seen = {
        str(item.get("artifactId") or item.get("name") or "")
        for item in merged
        if isinstance(item, dict)
    }
    for artifact in incoming or []:
        if not isinstance(artifact, dict):
            continue
        key = str(artifact.get("artifactId") or artifact.get("name") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(artifact)
    return merged


async def _apply_a2a_stream_event(
    a2a_result: Dict[str, Any],
    envelope: Dict[str, Any],
    status_callback: Optional[StatusCallback] = None,
    background_callback: Optional[BackgroundCallback] = None,
) -> Dict[str, Any]:
    if "error" in envelope:
        logger.error("[A2A] Agent returned stream error: %s", envelope["error"])
        raise Exception(f"Agent error: {envelope['error']}")

    event = envelope.get("result", {})
    if not isinstance(event, dict):
        return a2a_result

    # Heartbeat keepalives exist only to hold the connection open; they carry no
    # payload, so skip them before they can overwrite accumulated status/artifacts.
    event_metadata = event.get("metadata")
    if isinstance(event_metadata, dict) and event_metadata.get("heartbeat"):
        return a2a_result

    # declare_long_running: the agent asks the orchestrator to detach this turn.
    if background_callback and isinstance(event_metadata, dict) and event_metadata.get("background"):
        await background_callback(event_metadata)

    kind = str(event.get("kind") or "").strip().lower()
    if kind == "status-update":
        a2a_result["id"] = event.get("taskId") or a2a_result.get("id")
        a2a_result["contextId"] = event.get("contextId") or a2a_result.get("contextId")
        a2a_result["status"] = event.get("status", {})
        status_text = _extract_status_message_text(a2a_result["status"])
        if status_callback and status_text and not bool(event.get("final")):
            await status_callback(status_text)
    elif kind == "artifact-update":
        artifact = event.get("artifact")
        if isinstance(artifact, dict):
            a2a_result["artifacts"] = _merge_a2a_artifacts(
                a2a_result.get("artifacts", []),
                [artifact],
            )

    return a2a_result


async def _stream_a2a_agent(
    endpoint: str,
    message: Dict[str, Any],
    headers: Dict[str, str],
    timeout_seconds: float,
    status_callback: Optional[StatusCallback] = None,
    background_callback: Optional[BackgroundCallback] = None,
) -> Dict[str, Any]:
    """Stream A2A task updates and collapse them into a final task payload."""
    a2a_result: Dict[str, Any] = {
        "kind": "task",
        "artifacts": [],
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        stream_headers = {
            **headers,
            "Accept": "text/event-stream, application/x-ndjson",
        }
        async with client.stream(
            "POST",
            endpoint,
            json=message,
            headers=stream_headers,
        ) as response:
            logger.debug("[A2A] Stream response status: %s", response.status_code)
            response.raise_for_status()

            content_type = str(response.headers.get("content-type") or "").lower()

            if "application/x-ndjson" in content_type:
                async for line in response.aiter_lines():
                    payload = str(line or "").strip()
                    if not payload:
                        continue
                    envelope = json.loads(payload)
                    a2a_result = await _apply_a2a_stream_event(
                        a2a_result,
                        envelope,
                        status_callback=status_callback,
                        background_callback=background_callback,
                    )
            elif "text/event-stream" in content_type:
                data_lines: List[str] = []
                async for line in response.aiter_lines():
                    raw_line = str(line or "")
                    stripped = raw_line.strip()
                    if not stripped:
                        if data_lines:
                            envelope = json.loads("\n".join(data_lines))
                            a2a_result = await _apply_a2a_stream_event(
                                a2a_result,
                                envelope,
                                status_callback=status_callback,
                                background_callback=background_callback,
                            )
                            data_lines = []
                        continue
                    if stripped.startswith(":"):
                        continue
                    if stripped.startswith("data:"):
                        data_lines.append(stripped[5:].lstrip())

                if data_lines:
                    envelope = json.loads("\n".join(data_lines))
                    a2a_result = await _apply_a2a_stream_event(
                        a2a_result,
                        envelope,
                        status_callback=status_callback,
                        background_callback=background_callback,
                    )
            else:
                raise Exception(
                    f"Unsupported streaming content type from A2A proxy: {content_type or 'unknown'}"
                )

    return a2a_result


def is_self_agent(agent_id: str, agent_url: str) -> bool:
    """Return True when a discovered agent record points to this orchestrator.

    Primary check: agent_id (the LiteLLM routing key) matches the container
    hostname, which Docker Compose sets to the service name. URL comparison is
    a fallback for cases where the hostname-derived URL is available.
    """
    if _SELF_AGENT_ID and (agent_id or "").strip() == _SELF_AGENT_ID:
        return True
    return _normalize_url(agent_url) == _normalize_url(SELF_AGENT_URL)


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
        response = await client.get(f"{REGISTRY_URL}/v1/agents")
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
            response = await client.get(f"{REGISTRY_URL}/a2a/{agent_id}")
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


def _extract_status_payload(a2a_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract a structured payload from status.message text or data parts."""
    status = a2a_result.get("status", {})
    status_message = status.get("message", {})
    parts = status_message.get("parts", []) if isinstance(status_message, dict) else []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_kind = str(part.get("kind") or "").strip().lower()
        if part_kind == "data":
            data_payload = part.get("data")
            if isinstance(data_payload, dict):
                return data_payload
            continue
        if part_kind != "text":
            continue
        text_content = part.get("text")
        try:
            parsed = json.loads(text_content)
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse final status message as JSON: {e}")
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


async def call_a2a_agent(
    agent_url: str,
    skill_id: str,
    *,
    _prefer_streaming: bool = False,
    _status_callback: Optional[StatusCallback] = None,
    _background_callback: Optional[BackgroundCallback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Call an A2A agent using JSON-RPC protocol.

    Implements the Agent-to-Agent (A2A) communication protocol for invoking
    remote agent skills. Uses JSON-RPC with blocking=True for standard sends,
    and switches to the A2A SSE stream endpoint when the downstream agent card
    advertises streaming support.

    The response extraction expects the canonical final response in
    result.status.message.parts[*].text and separately normalizes native
    A2A artifacts from result.artifacts.

    Args:
        agent_url: Base URL of the agent
        skill_id: The skill ID to invoke
        _prefer_streaming: Whether to use streaming mode
        _status_callback: Callback for intermediate status updates
        **kwargs: Parameters for the skill

    Returns:
        Agent's response (unwrapped from A2A protocol)
    """
    request_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    logger.debug("[A2A] Calling agent at %s, skill: %s", agent_url, skill_id)

    # Build A2A JSON-RPC message
    message = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": [],
                "metadata": {"skillId": skill_id},
            },
            "configuration": {
                "blocking": True,  # Wait for task to complete before returning
            },
        }
    }

    request_params = {
        key: value
        for key, value in kwargs.items()
        if not key.startswith("_") and key != "provided_inputs"
    }
    if request_params:
        message["params"]["message"]["parts"].append(
            {
                "kind": "text",
                "text": json.dumps(request_params),
            }
        )
    provided_inputs = kwargs.get("provided_inputs")
    if isinstance(provided_inputs, dict) and provided_inputs:
        message["params"]["message"]["parts"].append(
            {
                "kind": "data",
                "data": {
                    "provided_inputs": provided_inputs,
                },
            }
        )
    # Propagate the conversation scope as the A2A contextId so downstream
    # agents see RequestContext.context_id == conversation_id. This is what
    # scopes the ArtifactRegistry and ContextStateStore on the specialist
    # side. The INPUT_REQUIRED resume path overrides it with the contextId
    # echoed by the downstream agent, which is the same value once the
    # initial call carried it.
    a2a_context_id = kwargs.get("_a2a_context_id") or kwargs.get("conversation_id")
    if a2a_context_id:
        message["params"]["message"]["contextId"] = str(a2a_context_id)
    if kwargs.get("_a2a_task_id"):
        message["params"]["message"]["taskId"] = kwargs["_a2a_task_id"]

    # Route through LiteLLM: agent_url is {REGISTRY_URL}/a2a/{agent_name}
    # LiteLLM's A2A endpoint requires the method in the URL path.
    endpoint = agent_url.rstrip("/") + "/message/send"
    headers = {"Content-Type": "application/json"}
    if LITELLM_MASTER_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_MASTER_KEY}"

    # Use longer timeout for research agents that may take minutes
    timeout_seconds = 900.0  # 15 minutes

    try:
        if _prefer_streaming:
            stream_message = dict(message)
            stream_message["method"] = "message/stream"
            # A2A streaming stays on the same JSON-RPC endpoint and switches the
            # method in the payload; LiteLLM does not expose a separate
            # /message/stream sub-route.
            stream_endpoint = agent_url.rstrip("/")
            logger.debug("[A2A] Using streaming invocation via %s", stream_endpoint)
            a2a_result = await _stream_a2a_agent(
                stream_endpoint,
                stream_message,
                headers,
                timeout_seconds,
                status_callback=_status_callback if callable(_status_callback) else None,
                background_callback=_background_callback if callable(_background_callback) else None,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(endpoint, json=message, headers=headers)
                logger.debug("[A2A] Response status: %s", response.status_code)
                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    logger.error("[A2A] Agent returned error: %s", result["error"])
                    raise Exception(f"Agent error: {result['error']}")

                logger.debug("[A2A] Got result: %s", str(result)[:500])

                # Extract the actual response from A2A protocol wrapper
                a2a_result = result.get("result", {})

        logger.debug("[A2A] Full result structure: %s", json.dumps(a2a_result, indent=2, default=str)[:2000])

        normalized_artifacts = _normalize_a2a_artifacts(
            a2a_result.get("artifacts", []),
            conversation_id=str(kwargs.get("conversation_id") or ""),
        )

        status = a2a_result.get("status", {})
        state = str(status.get("state") or "").strip().lower()
        parsed = _extract_status_payload(a2a_result)
        if state == "input-required":
            payload = parsed if isinstance(parsed, dict) else {}
            return {
                "status": "input_required",
                "input_required": payload,
                "_a2a_context_id": a2a_result.get("contextId"),
                "_a2a_task_id": a2a_result.get("id"),
            }
        if isinstance(parsed, dict):
            if normalized_artifacts and "artifacts" not in parsed:
                parsed = {**parsed, "artifacts": normalized_artifacts}
            return parsed

        error_payload: Dict[str, Any] = {
            "status": "error",
            "message": "Agent response missing canonical final status payload.",
        }
        if normalized_artifacts:
            error_payload["artifacts"] = normalized_artifacts
        return error_payload
    except httpx.TimeoutException:
        raise Exception(f"Agent request timed out after {timeout_seconds}s")
    except httpx.HTTPStatusError:
        raise
    except Exception:
        raise


async def create_tool_from_skill(
    agent_url: str,
    skill: Dict[str, Any],
    supports_streaming: bool = False,
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
            result = await call_a2a_agent(
                agent_url,
                skill_id,
                _prefer_streaming=supports_streaming,
                **remapped,
            )
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
        logger.warning("Failed to discover agents from registry: %s", e)
        return []

    tools = []

    for agent in agents:
        try:
            agent_id = agent["agent_id"]
            direct_url = agent["url"]   # downstream URL, used only for self-check

            # Never expose this orchestrator's own skills as dynamic tools.
            if is_self_agent(agent_id, direct_url):
                logger.debug("Skipping self agent in tool discovery: %s (%s)", agent_id, direct_url)
                continue

            # Route all calls through LiteLLM rather than directly to the agent.
            agent_url = f"{REGISTRY_URL}/a2a/{agent_id}"

            # LiteLLM's /v1/agents payload can omit full per-skill metadata.
            # Fetch the full card so tool schemas stay authoritative.
            agent_card = await get_agent_card(agent_id, direct_url=direct_url)
            if not agent_card.get("skills"):
                agent_card = agent.get("agent_card_params") or agent_card
            supports_streaming = bool((agent_card.get("capabilities") or {}).get("streaming", False))

            # Create one tool per skill
            for skill in agent_card.get("skills", []):
                tool = await create_tool_from_skill(
                    agent_url,
                    skill,
                    supports_streaming=supports_streaming,
                )
                tools.append(tool)
                logger.debug("Discovered tool: %s from %s", skill["id"], agent_id)
        except Exception as e:
            logger.warning("Failed to create tools for agent %s: %s", agent_id, e)
            continue

    logger.info("Total tools discovered: %d", len(tools))
    return tools
