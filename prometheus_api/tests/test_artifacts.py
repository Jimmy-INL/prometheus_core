"""Tests for artifact reference management."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from prometheus_api.agent import EventQueue, PrometheusAgent, RequestContext
from prometheus_api.agent.artifacts import ArtifactReference, ArtifactRegistry


class _DummyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        return {"ok": True}


def _extract_text_part(event) -> str:
    part = event.artifact.parts[0]
    if hasattr(part, "text"):
        return part.text
    if hasattr(part, "root") and hasattr(part.root, "text"):
        return part.root.text
    raise AssertionError("Unsupported artifact part structure")


def test_artifact_registry_conversation_scoping():
    registry = ArtifactRegistry(redis_url="redis://localhost:0", ttl_seconds=60)

    ref_a = ArtifactReference(
        artifact_id="a-id",
        conversation_id="conv-a",
        name="CAD Model",
        description="primary model",
        uri="file:///tmp/model.step",
    )
    ref_b = ArtifactReference(
        artifact_id="b-id",
        conversation_id="conv-b",
        name="Mesh",
        description="generated mesh",
        uri="file:///tmp/model.msh",
    )

    registry.register(ref_a)
    registry.register(ref_b)

    assert registry.resolve_by_id("conv-a", "a-id") is not None
    assert registry.resolve_by_id("conv-b", "a-id") is None
    assert registry.resolve_by_name("conv-a", "cad model").artifact_id == "a-id"
    assert len(registry.list("conv-a")) == 1
    assert len(registry.list("conv-b")) == 1


def test_send_json_artifact_auto_registers_reference():
    agent = _DummyAgent(agent_name="Test Agent")
    context = MagicMock(spec=RequestContext)
    context.task_id = "task-1"
    context.context_id = "conv-auto"
    queue = AsyncMock(spec=EventQueue)

    payload = {
        "name": "CAD Model",
        "description": "Rotor CAD output",
        "uri": "file:///tmp/rotor.step",
        "mime_type": "model/step",
    }

    asyncio.run(
        agent.send_json_artifact(
            context=context,
            event_queue=queue,
            payload=payload,
            name="artifact",
        )
    )

    registered = agent.resolve_artifact_by_name("conv-auto", "cad model")
    assert registered is not None
    assert registered.uri == "file:///tmp/rotor.step"

    event = queue.enqueue_event.call_args[0][0]
    serialized = json.loads(_extract_text_part(event))
    assert serialized["artifact_id"] == registered.artifact_id
    assert serialized["conversation_id"] == "conv-auto"


def test_send_artifact_reference_registers_and_emits():
    agent = _DummyAgent(agent_name="Test Agent")
    context = MagicMock(spec=RequestContext)
    context.task_id = "task-2"
    context.context_id = "conv-ref"
    queue = AsyncMock(spec=EventQueue)

    reference = asyncio.run(
        agent.send_artifact_reference(
            context=context,
            event_queue=queue,
            name="Mesh Output",
            description="Hex mesh generated from CAD",
            uri="deeplynx://container/file/mesh-123",
            mime_type="application/octet-stream",
        )
    )

    assert reference.conversation_id == "conv-ref"
    assert reference.name == "Mesh Output"
    resolved = agent.resolve_artifact_reference("conv-ref", reference.artifact_id)
    assert resolved is not None
    assert resolved.uri == "deeplynx://container/file/mesh-123"
