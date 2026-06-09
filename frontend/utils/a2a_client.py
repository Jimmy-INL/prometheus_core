"""
A2A JSON-RPC client for communicating with the client-agent.
"""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

import httpx

# Canonical wire contract shared with the client-agent. Re-exported here so
# frontend modules keep importing ConversationResponse from utils.a2a_client.
from prometheus_api.contract import (  # noqa: F401
    ConversationResponse,
    ConversationStatus,
)


def response_from_payload(data: Dict[str, Any]) -> ConversationResponse:
    """Build a ConversationResponse from a client-agent response payload dict.

    Shared by the streaming parser and the background-task notifier (which
    renders a persisted result payload after a detached turn completes)."""
    return ConversationResponse.from_payload(data)


class A2AClient:
    """Async client for the A2A JSON-RPC protocol used by client-agent."""

    def __init__(self, agent_url: str, agent_secret: str, timeout: float = 900.0):
        self.agent_url = agent_url.rstrip("/")
        self.agent_secret = agent_secret
        self.timeout = timeout

    async def stage_upload(
        self,
        file_path: Path,
        *,
        name: str,
        mime_type: str,
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Stream upload bytes to the client-agent and return a staged upload token."""
        path = Path(file_path)
        headers = {
            "Content-Type": mime_type or "application/octet-stream",
            "Content-Length": str(path.stat().st_size),
            "Authorization": f"Bearer {self.agent_secret}",
        }
        params = {
            "name": name,
            "mime_type": mime_type or "application/octet-stream",
            "conversation_id": conversation_id,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agent_url}/uploads/stage",
                params=params,
                headers=headers,
                content=self._file_chunks(path),
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not payload.get("upload_id"):
            raise ValueError("Upload staging response did not include upload_id")
        return payload

    async def _file_chunks(self, file_path: Path, chunk_size: int = 1024 * 1024):
        with Path(file_path).open("rb") as stream:
            while True:
                chunk = await asyncio.to_thread(stream.read, chunk_size)
                if not chunk:
                    break
                yield chunk

    async def send(
        self,
        query: str,
        conversation_id: str,
        artifacts: Optional[List[Dict]] = None,
        followup_answers: Optional[Dict] = None,
        plan_approved: Optional[bool] = False,
        plan_rejected: Optional[bool] = False,
        workflow_id: Optional[str] = None,
        uploaded_files: Optional[List[Dict]] = None,
        on_status: Optional[Callable[[str], Coroutine]] = None,
    ) -> ConversationResponse:
        """Send a message to the client-agent via A2A JSON-RPC streaming."""
        request_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        # Build the inner payload (ConversationRequest fields)
        payload: Dict[str, Any] = {
            "query": query,
            "conversation_id": conversation_id,
        }
        if artifacts:
            payload["artifacts"] = artifacts
        if followup_answers:
            payload["followup_answers"] = followup_answers
        if plan_approved:
            payload["plan_approved"] = True
        if plan_rejected:
            payload["plan_rejected"] = True
        if workflow_id:
            payload["workflow_id"] = workflow_id
        if uploaded_files:
            payload["uploaded_files"] = uploaded_files

        # A2A JSON-RPC envelope
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/stream",
            "params": {
                "message": {
                    "messageId": message_id,
                    "role": "user",
                    # contextId is the A2A-spec conversation scope; the a2a-sdk
                    # exposes it to the client-agent as RequestContext.context_id.
                    "contextId": conversation_id,
                    "parts": [
                        {
                            # "kind" is the A2A SDK part discriminator
                            "kind": "text",
                            "text": json.dumps(payload),
                        }
                    ],
                },
                "configuration": {"blocking": True},
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/x-ndjson",
            "Authorization": f"Bearer {self.agent_secret}",
        }

        result = await self._stream_request(message, headers, on_status=on_status)

        return self._parse_response(result, conversation_id)

    async def _stream_request(
        self,
        message: Dict[str, Any],
        headers: Dict[str, str],
        *,
        on_status: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        """Stream A2A events and return a blocking-style JSON-RPC result."""
        a2a_result: Dict[str, Any] = {"kind": "task", "artifacts": []}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                self.agent_url,
                json=message,
                headers=headers,
            ) as response:
                response.raise_for_status()
                content_type = str(response.headers.get("content-type") or "").lower()

                if "application/x-ndjson" in content_type:
                    async for line in response.aiter_lines():
                        payload = str(line or "").strip()
                        if payload:
                            envelope = json.loads(payload)
                            a2a_result = await self._apply_stream_event(
                                a2a_result,
                                envelope,
                                on_status=on_status,
                            )
                elif "text/event-stream" in content_type:
                    data_lines: List[str] = []
                    async for line in response.aiter_lines():
                        stripped = str(line or "").strip()
                        if not stripped:
                            if data_lines:
                                envelope = json.loads("\n".join(data_lines))
                                a2a_result = await self._apply_stream_event(
                                    a2a_result,
                                    envelope,
                                    on_status=on_status,
                                )
                                data_lines = []
                            continue
                        if stripped.startswith(":"):
                            continue
                        if stripped.startswith("data:"):
                            data_lines.append(stripped[5:].lstrip())

                    if data_lines:
                        envelope = json.loads("\n".join(data_lines))
                        a2a_result = await self._apply_stream_event(
                            a2a_result,
                            envelope,
                            on_status=on_status,
                        )
                else:
                    raise ValueError(
                        f"Unsupported A2A streaming content type: {content_type or 'unknown'}"
                    )

        return {"result": a2a_result}

    async def _apply_stream_event(
        self,
        a2a_result: Dict[str, Any],
        envelope: Dict[str, Any],
        *,
        on_status: Optional[Callable[[str], Coroutine]] = None,
    ) -> Dict[str, Any]:
        if "error" in envelope:
            raise ValueError(f"Agent stream error: {envelope['error']}")

        event = envelope.get("result", {})
        if not isinstance(event, dict):
            return a2a_result

        # Heartbeat keepalives only hold the connection open; they carry no
        # payload, so skip them before they can overwrite accumulated state.
        event_metadata = event.get("metadata")
        if isinstance(event_metadata, dict) and event_metadata.get("heartbeat"):
            return a2a_result

        kind = str(event.get("kind") or "").strip().lower()
        if kind == "status-update":
            a2a_result["id"] = event.get("taskId") or a2a_result.get("id")
            a2a_result["contextId"] = event.get("contextId") or a2a_result.get("contextId")
            a2a_result["status"] = event.get("status", {})
            status_text = self._extract_status_message_text(a2a_result["status"])
            if on_status and status_text and not bool(event.get("final")):
                await on_status(status_text)
        elif kind == "artifact-update":
            artifact = event.get("artifact")
            if isinstance(artifact, dict):
                a2a_result["artifacts"] = self._merge_stream_artifacts(
                    a2a_result.get("artifacts", []),
                    [artifact],
                )

        return a2a_result

    def _extract_status_message_text(self, status_payload: Dict[str, Any]) -> str:
        message = status_payload.get("message", {}) if isinstance(status_payload, dict) else {}
        parts = message.get("parts", []) if isinstance(message, dict) else []
        for part in parts:
            if not isinstance(part, dict):
                continue
            root = part.get("root") if isinstance(part.get("root"), dict) else None
            part_kind = str(part.get("kind") or (root or {}).get("kind") or "").strip().lower()
            if part_kind != "text":
                continue
            text = part.get("text")
            if text is None and root is not None:
                text = root.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        return ""

    def _merge_stream_artifacts(
        self,
        existing: List[Dict[str, Any]],
        incoming: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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

    def _parse_response(self, result: Dict[str, Any], fallback_conv_id: str) -> ConversationResponse:
        """Parse A2A JSON-RPC response into ConversationResponse.

        Expects the canonical final response in result.status.message.parts[].
        """
        a2a_result = result.get("result", {})

        parsed = self._extract_from_status(a2a_result)
        if parsed:
            return parsed

        return ConversationResponse(
            conversation_id=fallback_conv_id,
            status="error",
            message="Agent response missing canonical final status payload.",
        )

    def _extract_from_status(self, a2a_result: Dict) -> Optional[ConversationResponse]:
        """Extract ConversationResponse from status.message.parts."""
        status = a2a_result.get("status", {})
        message = status.get("message", {})
        parts = message.get("parts", [])

        for part in parts:
            if not isinstance(part, dict):
                continue
            root = part.get("root") if isinstance(part.get("root"), dict) else None
            part_kind = str(part.get("kind") or (root or {}).get("kind") or "").strip().lower()
            if part_kind != "text":
                continue
            text = part.get("text")
            if text is None and root is not None:
                text = root.get("text", "")
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "status" in data:
                    return self._dict_to_response(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _dict_to_response(self, data: Dict) -> ConversationResponse:
        """Convert a dict to ConversationResponse."""
        return response_from_payload(data)
