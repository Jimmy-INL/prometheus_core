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


def _extract_data_part(event):
    part = event.artifact.parts[0]
    if hasattr(part, "data"):
        return part.data
    if hasattr(part, "root") and hasattr(part.root, "data"):
        return part.root.data
    raise AssertionError("Unsupported data part structure")


def _extract_file_part(event):
    part = event.artifact.parts[0]
    if hasattr(part, "file"):
        return part.file
    if hasattr(part, "root") and hasattr(part.root, "file"):
        return part.root.file
    raise AssertionError("Unsupported file part structure")


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
    payload = _extract_data_part(event)
    assert payload["artifact_id"] == registered.artifact_id
    assert payload["conversation_id"] == "conv-auto"


def test_send_json_artifact_catalogs_inline_json_artifact():
    agent = _DummyAgent(agent_name="Test Agent")
    context = MagicMock(spec=RequestContext)
    context.task_id = "task-json"
    context.context_id = "conv-json"
    queue = AsyncMock(spec=EventQueue)

    payload = {"hello": "world"}

    artifact_id = asyncio.run(
        agent.send_json_artifact(
            context=context,
            event_queue=queue,
            payload=payload,
            name="Debug JSON",
            description="Inline debug payload",
            json_type="prometheus.debug.echo.v1",
            catalog_artifact=True,
        )
    )

    registered = agent.resolve_artifact_reference("conv-json", artifact_id)
    assert registered is not None
    assert registered.mime_type == "application/json"
    assert registered.json_type == "prometheus.debug.echo.v1"
    assert registered.json_body == payload

    event = queue.enqueue_event.call_args[0][0]
    assert _extract_data_part(event) == payload


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
    event = queue.enqueue_event.call_args[0][0]
    file_payload = _extract_file_part(event)
    assert file_payload.uri == "deeplynx://container/file/mesh-123"


def test_artifact_reference_from_a2a_file_part():
    payload = {
        "artifactId": "artifact-1",
        "name": "Mesh Output",
        "description": "Hex mesh generated from CAD",
        "parts": [
            {
                "kind": "file",
                "file": {
                    "uri": "deeplynx://container/file/mesh-123",
                    "mimeType": "application/octet-stream",
                    "name": "mesh.exo",
                },
            }
        ],
        "metadata": {
            "conversation_id": "conv-file",
            "producer_agent_id": "artifact-debug-agent",
            "created_at": "2026-03-18T00:00:00+00:00",
            "tags": ["mesh"],
        },
    }

    reference = ArtifactReference.from_a2a_artifact(payload)

    assert reference is not None
    assert reference.artifact_id == "artifact-1"
    assert reference.conversation_id == "conv-file"
    assert reference.uri == "deeplynx://container/file/mesh-123"
    assert reference.mime_type == "application/octet-stream"
    assert reference.tags == ["mesh"]


def test_artifact_reference_from_a2a_data_part():
    payload = {
        "artifactId": "artifact-2",
        "name": "Corrosion Summary",
        "description": "Inline analysis output",
        "parts": [
            {
                "kind": "data",
                "data": {"material_id": "Alloy 600", "finding_count": 3},
                "metadata": {
                    "mime_type": "application/json",
                    "json_type": "prometheus.analysis.corrosion_summary.v1",
                },
            }
        ],
        "metadata": {
            "conversation_id": "conv-data",
            "producer_agent_id": "analysis-agent",
            "created_at": "2026-03-18T00:00:00+00:00",
        },
    }

    reference = ArtifactReference.from_a2a_artifact(payload)

    assert reference is not None
    assert reference.artifact_id == "artifact-2"
    assert reference.conversation_id == "conv-data"
    assert reference.mime_type == "application/json"
    assert reference.json_type == "prometheus.analysis.corrosion_summary.v1"
    assert reference.json_body == {"material_id": "Alloy 600", "finding_count": 3}


def test_artifact_reference_preserves_data_part_metadata():
    payload = {
        "artifactId": "artifact-3",
        "name": "conversation_message",
        "parts": [
            {
                "kind": "data",
                "data": {"message": "Hello"},
                "metadata": {
                    "mime_type": "application/json",
                    "kind": "conversation_message",
                },
            }
        ],
        "metadata": {
            "conversation_id": "conv-data",
            "producer_agent_id": "analysis-agent",
        },
    }

    reference = ArtifactReference.from_a2a_artifact(payload)

    assert reference is not None
    assert reference.metadata["kind"] == "conversation_message"
