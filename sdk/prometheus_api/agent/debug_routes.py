"""Debug and compatibility HTTP routes for Prometheus agents."""

import json
import uuid
from typing import Any, Dict, cast

from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskStatusUpdateEvent
from starlette.responses import JSONResponse


class _LocalRequestContext:
    """Minimal RequestContext-compatible object for the debug chat endpoint."""

    def __init__(self, request_params: Dict[str, Any], task_id: str, context_id: str):
        self.task_id = task_id
        self.context_id = context_id
        self._request_params = request_params

    def get_user_input(self) -> str:
        return json.dumps(self._request_params)


class _CollectingEventQueue:
    """EventQueue-compatible collector used by the debug chat endpoint."""

    def __init__(self):
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def _extract_result_payload(events: list[Any]) -> Any:
    for event in reversed(events):
        if not isinstance(event, TaskStatusUpdateEvent) or not event.final:
            continue

        status_message = getattr(event.status, "message", None)
        if status_message is None:
            continue

        for part in getattr(status_message, "parts", []) or []:
            text_value = None
            if hasattr(part, "text"):
                text_value = part.text
            elif hasattr(part, "root") and hasattr(part.root, "text"):
                text_value = part.root.text

            if text_value is None:
                continue

            try:
                return json.loads(text_value)
            except Exception:
                return text_value
    return None


def _serialize_events(events: list[Any]) -> list[Dict[str, Any]]:
    serialized = []
    for event in events:
        if hasattr(event, "model_dump"):
            serialized.append(
                event.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
        else:
            serialized.append({"type": type(event).__name__, "value": str(event)})
    return serialized


def _params_from_body(body: Dict[str, Any]) -> Dict[str, Any] | JSONResponse:
    if isinstance(body.get("params"), dict):
        return dict(body["params"])
    if "message" in body:
        message_value = body.get("message")
        if isinstance(message_value, dict):
            return dict(message_value)
        if isinstance(message_value, str):
            try:
                parsed = json.loads(message_value)
                return parsed if isinstance(parsed, dict) else {"message": message_value}
            except Exception:
                return {"message": message_value}
        return JSONResponse(
            {"ok": False, "error": "message must be a string or object"},
            status_code=400,
        )

    # Last-resort compatibility: treat entire body as params except control keys.
    return {
        k: v
        for k, v in body.items()
        if k
        not in {
            "task_id",
            "context_id",
            "conversation_id",
            "include_events",
            "include_artifacts",
        }
    }


def add_debug_chat_route(app, *, agent: Any, executor: Any) -> None:
    """Register the compatibility/debug chat endpoint on a Starlette app."""

    async def api_chat(request):
        """
        Compatibility/debug chat endpoint.

        Accepts either:
        - {"message": "<text>"} or {"message": {...}}
        - {"params": {...}}

        Optional fields:
        - task_id, context_id, conversation_id
        - include_events (bool): include raw event payloads in response
        - include_artifacts (bool, default true): include conversation artifact catalog
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"ok": False, "error": "Invalid JSON body"},
                status_code=400,
            )

        if not isinstance(body, dict):
            return JSONResponse(
                {"ok": False, "error": "JSON body must be an object"},
                status_code=400,
            )

        params = _params_from_body(body)
        if isinstance(params, JSONResponse):
            return params

        task_id = str(body.get("task_id") or uuid.uuid4())
        context_id = str(body.get("context_id") or body.get("conversation_id") or uuid.uuid4())
        include_events = bool(body.get("include_events", False))
        include_artifacts = bool(body.get("include_artifacts", True))

        local_context = _LocalRequestContext(params, task_id=task_id, context_id=context_id)
        local_queue = _CollectingEventQueue()

        try:
            await executor.execute(
                cast(RequestContext, local_context),
                cast(EventQueue, local_queue),
            )
        except Exception as e:
            error_response = {
                "ok": False,
                "task_id": task_id,
                "context_id": context_id,
                "error": str(e),
            }
            if include_events:
                error_response["events"] = _serialize_events(local_queue.events)
            return JSONResponse(error_response, status_code=500)

        result_payload = _extract_result_payload(local_queue.events)
        final_state = None
        for event in reversed(local_queue.events):
            if isinstance(event, TaskStatusUpdateEvent):
                final_state = event.status.state.value
                break

        response_payload = {
            "ok": True,
            "task_id": task_id,
            "context_id": context_id,
            "state": final_state,
            "result": result_payload,
        }
        if include_events:
            response_payload["events"] = _serialize_events(local_queue.events)
        if include_artifacts:
            artifact_refs = [ref.to_dict() for ref in agent.list_artifact_references(context_id)]
            response_payload["artifacts"] = artifact_refs
            response_payload["artifact_lookup"] = {
                ref.get("name"): ref.get("artifact_id")
                for ref in artifact_refs
                if isinstance(ref.get("name"), str) and ref.get("name")
            }

        return JSONResponse(response_payload)

    app.add_route("/api/chat", api_chat, methods=["POST"])
