# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Client-side helpers for consuming A2A streaming responses.

The Prometheus frontend and the client-agent orchestrator both consume A2A
``SendStreamingMessage`` responses (SSE or NDJSON) and collapse the event stream
into a single blocking-style task payload. This module is the single
implementation of that logic; do not copy it into consumers.

Dependency-light by design (stdlib + httpx), so the frontend can import it
without the agent runtime (a2a-sdk, starlette, litellm).

Only A2A v1 envelope and part shapes are accepted. Pre-v1 dashed event kinds,
root-wrapped parts, and status-update ``final`` fields are intentionally not
supported.

Event handling rules:

- v1 ``statusUpdate`` events overwrite the accumulated ``status`` and update
  ``id``/``contextId``; non-stopping events with a text message invoke the
  ``status_callback``.
- v1 ``artifactUpdate`` events are merged into ``artifacts``, deduplicated by
  ``artifactId`` (falling back to ``name``).
- Heartbeat keepalives (``metadata.heartbeat``) carry no payload and are
  skipped before they can overwrite accumulated state.
- ``metadata.background`` (an agent calling ``declare_long_running``) invokes
  the ``background_callback`` once per tagged event.
- An ``error`` member in any envelope raises :class:`A2AStreamError`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], Awaitable[None]]
BackgroundCallback = Callable[[Dict[str, Any]], Awaitable[None]]
_TASK_STATES = {
    "TASK_STATE_UNSPECIFIED",
    "TASK_STATE_SUBMITTED",
    "TASK_STATE_WORKING",
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_REJECTED",
    "TASK_STATE_INPUT_REQUIRED",
    "TASK_STATE_AUTH_REQUIRED",
}
_STOPPING_STATES = {
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_REJECTED",
    "TASK_STATE_INPUT_REQUIRED",
    "TASK_STATE_AUTH_REQUIRED",
}


class A2AStreamError(Exception):
    """Raised when an A2A stream reports an error or cannot be parsed."""


def new_task_accumulator() -> Dict[str, Any]:
    """Return the empty accumulated-task payload a stream collapses into."""
    return {"kind": "task", "artifacts": []}


def extract_status_message_text(status_payload: Any) -> str:
    """Extract plain text from a ``status.message`` payload.

    A2A v1 represents text with a direct ``Part.text`` JSON field.
    """
    message = status_payload.get("message", {}) if isinstance(status_payload, dict) else {}
    parts = message.get("parts", []) if isinstance(message, dict) else []
    for part in parts:
        if not isinstance(part, dict):
            raise A2AStreamError("A2A v1 status message Part must be an object")
        unexpected = set(part) - {
            "text",
            "raw",
            "url",
            "data",
            "metadata",
            "filename",
            "mediaType",
        }
        if unexpected:
            raise A2AStreamError(
                f"A2A v1 status message Part has unsupported fields: {sorted(unexpected)}"
            )
        content_fields = [field for field in ("text", "raw", "url", "data") if field in part]
        if len(content_fields) != 1:
            raise A2AStreamError(
                "A2A v1 status message Part must contain exactly one content field"
            )
        if content_fields[0] != "text":
            continue
        text = part.get("text")
        if not isinstance(text, str):
            raise A2AStreamError("A2A v1 status message Part.text must be a string")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _validate_task_status(status: Any) -> Dict[str, Any]:
    """Return an exact A2A v1 status or reject its malformed task state."""
    if not isinstance(status, dict):
        raise A2AStreamError("A2A v1 task status must be an object")
    state = status.get("state")
    if state not in _TASK_STATES:
        raise A2AStreamError(
            "A2A v1 task status.state must be an exact TASK_STATE_* ProtoJSON value"
        )
    return dict(status)


def merge_artifacts(
    existing: Optional[List[Dict[str, Any]]],
    incoming: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Merge artifact dicts preserving order, deduplicated by artifactId/name."""
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


async def apply_stream_event(
    a2a_result: Dict[str, Any],
    envelope: Dict[str, Any],
    *,
    status_callback: Optional[StatusCallback] = None,
    background_callback: Optional[BackgroundCallback] = None,
) -> Dict[str, Any]:
    """Fold one A2A v1 stream envelope into the accumulated task payload."""
    if "error" in envelope:
        raise A2AStreamError(f"Agent error: {envelope['error']}")

    result = envelope.get("result")
    if not isinstance(result, dict):
        raise A2AStreamError("A2A v1 stream envelope result must be an object")

    payload_fields = [
        field for field in ("task", "message", "statusUpdate", "artifactUpdate") if field in result
    ]
    if len(payload_fields) != 1:
        raise A2AStreamError("A2A v1 stream result must contain exactly one StreamResponse payload")
    payload_field = payload_fields[0]
    if payload_field == "message":
        raise A2AStreamError(
            "Prometheus streaming agents must return a task, not a standalone message"
        )

    if payload_field == "task":
        task = result["task"]
        if not isinstance(task, dict):
            raise A2AStreamError("A2A v1 StreamResponse.task must be an object")
        a2a_result["id"] = task.get("id") or a2a_result.get("id")
        a2a_result["contextId"] = task.get("contextId") or a2a_result.get("contextId")
        if "status" not in task:
            raise A2AStreamError("A2A v1 Task.status is required")
        a2a_result["status"] = _validate_task_status(task["status"])
        if isinstance(task.get("artifacts"), list):
            a2a_result["artifacts"] = merge_artifacts(
                a2a_result.get("artifacts", []),
                task["artifacts"],
            )
        return a2a_result

    if payload_field == "statusUpdate":
        event = result["statusUpdate"]
        event_type = "status"
    else:
        event = result["artifactUpdate"]
        event_type = "artifact"
    if not isinstance(event, dict):
        raise A2AStreamError(f"A2A v1 StreamResponse.{payload_field} must be an object")

    # Heartbeat keepalives only hold the connection open; they carry no
    # payload, so skip them before they can overwrite accumulated state.
    event_metadata = event.get("metadata")
    if isinstance(event_metadata, dict) and event_metadata.get("heartbeat"):
        return a2a_result

    # declare_long_running: the agent asks the caller to detach this turn.
    if (
        background_callback
        and isinstance(event_metadata, dict)
        and event_metadata.get("background")
    ):
        await background_callback(event_metadata)

    if event_type == "status":
        a2a_result["id"] = event.get("taskId") or a2a_result.get("id")
        a2a_result["contextId"] = event.get("contextId") or a2a_result.get("contextId")
        a2a_result["status"] = _validate_task_status(event.get("status"))
        status_text = extract_status_message_text(a2a_result["status"])
        state = a2a_result["status"]["state"]
        is_stopping = state in _STOPPING_STATES
        if status_callback and status_text and not is_stopping:
            await status_callback(status_text)
    else:
        artifact = event.get("artifact")
        if not isinstance(artifact, dict):
            raise A2AStreamError("A2A v1 artifactUpdate.artifact must be an object")
        a2a_result["artifacts"] = merge_artifacts(
            a2a_result.get("artifacts", []),
            [artifact],
        )

    return a2a_result


async def consume_stream_response(
    response: httpx.Response,
    *,
    status_callback: Optional[StatusCallback] = None,
    background_callback: Optional[BackgroundCallback] = None,
) -> Dict[str, Any]:
    """Collapse an open httpx streaming response into a final task payload.

    Supports ``application/x-ndjson`` (one JSON envelope per line) and
    ``text/event-stream`` (SSE ``data:`` blocks). A JSON response is consumed
    as one envelope so a pre-stream JSON-RPC error is reported to the caller.
    Raises :class:`A2AStreamError` for any other content type.
    """
    a2a_result = new_task_accumulator()
    content_type = str(response.headers.get("content-type") or "").lower()

    if "application/x-ndjson" in content_type:
        async for line in response.aiter_lines():
            payload = str(line or "").strip()
            if not payload:
                continue
            envelope = json.loads(payload)
            a2a_result = await apply_stream_event(
                a2a_result,
                envelope,
                status_callback=status_callback,
                background_callback=background_callback,
            )
    elif "text/event-stream" in content_type:
        data_lines: List[str] = []

        async def _flush() -> None:
            nonlocal a2a_result, data_lines
            if data_lines:
                envelope = json.loads("\n".join(data_lines))
                a2a_result = await apply_stream_event(
                    a2a_result,
                    envelope,
                    status_callback=status_callback,
                    background_callback=background_callback,
                )
                data_lines = []

        async for line in response.aiter_lines():
            stripped = str(line or "").strip()
            if not stripped:
                await _flush()
                continue
            if stripped.startswith(":"):
                continue
            if stripped.startswith("data:"):
                data_lines.append(stripped[5:].lstrip())
        await _flush()
    elif "application/json" in content_type:
        payload = "\n".join([line async for line in response.aiter_lines()]).strip()
        if not payload:
            raise A2AStreamError("A2A streaming endpoint returned an empty JSON response")
        a2a_result = await apply_stream_event(
            a2a_result,
            json.loads(payload),
            status_callback=status_callback,
            background_callback=background_callback,
        )
    else:
        raise A2AStreamError(f"Unsupported A2A streaming content type: {content_type or 'unknown'}")

    return a2a_result


async def stream_a2a_request(
    endpoint: str,
    message: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 900.0,
    status_callback: Optional[StatusCallback] = None,
    background_callback: Optional[BackgroundCallback] = None,
) -> Dict[str, Any]:
    """POST a JSON-RPC message to an A2A streaming endpoint and collapse the
    resulting event stream into a final task payload."""
    stream_headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/x-ndjson",
        "A2A-Version": "1.0",
        **(headers or {}),
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with client.stream(
            "POST",
            endpoint,
            json=message,
            headers=stream_headers,
        ) as response:
            logger.debug("[A2A] Stream response status: %s", response.status_code)
            response.raise_for_status()
            return await consume_stream_response(
                response,
                status_callback=status_callback,
                background_callback=background_callback,
            )
