"""
A2A JSON-RPC client for communicating with the client-agent.
"""
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

import httpx


@dataclass
class ConversationResponse:
    """Parsed response from the client-agent."""

    conversation_id: str
    status: str  # "needs_info" | "plan_ready" | "executing" | "completed" | "recommendation" | "answer"
    message: Optional[str] = None
    followup_questions: Optional[List[Dict]] = None
    plan: Optional[Dict] = None
    report: Optional[str] = None
    tool_results: Optional[Dict] = None
    response_text: Optional[str] = None
    recommended_materials: Optional[List[str]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None  # full conversation catalog
    new_artifacts: Optional[List[Dict[str, Any]]] = None  # only produced this turn
    message_metadata: Optional[Dict[str, Any]] = None


class A2AClient:
    """Async client for the A2A JSON-RPC protocol used by client-agent."""

    def __init__(self, agent_url: str, agent_secret: str, timeout: float = 900.0):
        self.agent_url = agent_url.rstrip("/")
        self.agent_secret = agent_secret
        self.timeout = timeout

    async def send(
        self,
        query: str,
        conversation_id: str,
        artifacts: Optional[List[Dict]] = None,
        followup_answers: Optional[Dict] = None,
        plan_approved: Optional[bool] = False,
        workflow_id: Optional[str] = None,
        on_status: Optional[Callable[[str], Coroutine]] = None,
    ) -> ConversationResponse:
        """Send a message to the client-agent via A2A JSON-RPC.

        Args:
            on_status: Optional async callback invoked with status text during long-running
                       operations. The client polls /status/{conversation_id} every 3 seconds
                       and calls this with each new status message.
        """
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
        if workflow_id:
            payload["workflow_id"] = workflow_id

        # A2A JSON-RPC envelope
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
                            "text": json.dumps(payload),
                        }
                    ],
                },
                "configuration": {"blocking": True},
                "context": {
                    "conversationId": conversation_id,
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.agent_secret}",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            send_task = asyncio.create_task(
                client.post(self.agent_url, json=message, headers=headers)
            )

            # Poll for status updates while the blocking call is in flight
            if on_status:
                poll_task = asyncio.create_task(
                    self._poll_status(client, conversation_id, headers, on_status, send_task)
                )

            response = await send_task

            if on_status:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass

            response.raise_for_status()
            result = response.json()

        return self._parse_response(result, conversation_id)

    async def _poll_status(
        self,
        client: httpx.AsyncClient,
        conversation_id: str,
        headers: Dict[str, str],
        on_status: Callable[[str], Coroutine],
        send_task: asyncio.Task,
    ) -> None:
        """Poll the status endpoint and invoke on_status with new messages."""
        seen_count = 0
        status_url = f"{self.agent_url}/status/{conversation_id}"
        await asyncio.sleep(2)  # Initial delay before first poll
        while not send_task.done():
            try:
                resp = await client.get(status_url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    history = data.get("history", [])
                    for entry in history[seen_count:]:
                        msg = entry.get("message", "") if isinstance(entry, dict) else str(entry)
                        if msg:
                            await on_status(msg)
                    seen_count = len(history)
            except Exception:
                pass
            await asyncio.sleep(3)

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
            part_kind = str(part.get("kind") or part.get("type") or (root or {}).get("kind") or "").strip().lower()
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
        return ConversationResponse(
            conversation_id=data.get("conversation_id", ""),
            status=data.get("status", "answer"),
            message=data.get("message"),
            followup_questions=data.get("followup_questions"),
            plan=data.get("plan"),
            report=data.get("report"),
            tool_results=data.get("tool_results"),
            response_text=data.get("response_text"),
            recommended_materials=data.get("recommended_materials"),
            artifacts=data.get("artifacts"),
            new_artifacts=data.get("new_artifacts"),
            message_metadata=data.get("message_metadata"),
        )
