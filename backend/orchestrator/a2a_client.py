"""
Async A2A (Agent-to-Agent) client for making calls to A2A-compliant agents.

Uses the standard A2A JSON-RPC protocol (tasks/send) over HTTP.
"""

import logging
import uuid

import httpx

log = logging.getLogger(__name__)


class A2AError(Exception):
    """Raised when an A2A call fails."""

    def __init__(self, message: str, code: int | None = None, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.data = data


async def send_task(
    endpoint: str,
    message: str | None = None,
    *,
    task_id: str | None = None,
    timeout: float = 60.0,
    headers: dict[str, str] | None = None,
) -> str:
    """Send a task to an A2A agent and return the text response.

    Args:
        endpoint: The agent's A2A endpoint URL (e.g. "http://localhost:8300").
        message: The text prompt to send. If None, sends empty parts list.
        task_id: Optional task ID. A UUID is generated if not provided.
        timeout: Request timeout in seconds.
        headers: Optional extra HTTP headers (e.g. for auth).

    Returns:
        The agent's text response extracted from the A2A result.

    Raises:
        A2AError: If the agent returns a JSON-RPC error or the response
            cannot be parsed.
        httpx.HTTPStatusError: If the HTTP request fails.
    """
    task_id = task_id or uuid.uuid4().hex
    request_id = uuid.uuid4().hex

    message_id = uuid.uuid4().hex
    parts = [{"kind": "text", "text": message}] if message else []

    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id,
                "role": "user",
                "parts": parts,
            },
        },
        "id": request_id,
    }

    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    log.debug("A2A request to %s: %s", endpoint, payload)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(endpoint, json=payload, headers=request_headers)
        if resp.status_code >= 400:
            log.error(
                "A2A HTTP %d from %s — body: %s",
                resp.status_code,
                endpoint,
                resp.text,
            )
            raise A2AError(
                f"HTTP {resp.status_code}: {resp.text}",
                code=resp.status_code,
            )
        body = resp.json()

    if "error" in body:
        err = body["error"]
        raise A2AError(
            message=err.get("message", "Unknown A2A error"),
            code=err.get("code"),
            data=err.get("data"),
        )

    import time
    time.sleep(3)
    return _extract_text(body)


def _is_text_part(part: dict) -> bool:
    """Check if a part is a text part (handles both 'type' and 'kind' fields)."""
    return part.get("type") == "text" or part.get("kind") == "text"


def _extract_text(body: dict) -> str:
    """Pull the agent's text out of a message/send JSON-RPC response."""
    try:
        result = body["result"]
        log.debug("A2A response result: %s", result)

        # Check artifacts first (where most agent responses live)
        for artifact in result.get("artifacts", []):
            art_parts = artifact.get("parts", [])
            text_parts = [p["text"] for p in art_parts if _is_text_part(p)]
            if text_parts:
                return "\n".join(text_parts)

        # Fall back to status.message
        status = result.get("status", {})
        status_msg = status.get("message", {})
        parts = status_msg.get("parts", [])
        text_parts = [p["text"] for p in parts if _is_text_part(p)]
        if text_parts:
            return "\n".join(text_parts)

        raise A2AError("No text content found in A2A response")
    except KeyError as exc:
        raise A2AError(f"Unexpected A2A response structure: missing {exc}") from exc
