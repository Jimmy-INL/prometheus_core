"""A2A event helpers shared by Prometheus agent executors and agent helpers."""

import uuid
from typing import Any, Dict, Optional

from a2a.server.agent_execution.context import RequestContext
from a2a.types import Message, Part, Role, TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart


def context_task_id(context: RequestContext) -> str:
    """Return a non-null task ID for A2A event models."""
    return str(getattr(context, "task_id", "") or "")


def context_id(context: RequestContext) -> str:
    """Return a non-null context ID for A2A event models."""
    return str(getattr(context, "context_id", "") or "")


def build_status_update_event(
    *,
    context: RequestContext,
    state: TaskState,
    final: bool,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskStatusUpdateEvent:
    """Build a task status update event with an optional text message."""
    task_id = context_task_id(context)
    current_context_id = context_id(context)
    status_message = None
    if message:
        status_message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=message))],
            context_id=current_context_id,
            task_id=task_id,
        )

    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=current_context_id,
        final=final,
        status=TaskStatus(state=state, message=status_message),
        metadata=metadata,
    )


async def emit_status_update(
    *,
    context: RequestContext,
    event_queue: Any,
    state: TaskState,
    final: bool,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Build and enqueue a task status update event."""
    await event_queue.enqueue_event(
        build_status_update_event(
            context=context,
            state=state,
            final=final,
            message=message,
            metadata=metadata,
        )
    )
