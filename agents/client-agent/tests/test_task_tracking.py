"""Tests for orchestrator → Task Graph integration (task_tracking).

These exercise the turn/skill lifecycle against an in-memory fake Redis, the
same fixture style as test_task_graph. The client-agent suite has no async
plugin, so coroutines are driven with ``asyncio.run`` (matching the existing
tests) and a whole turn runs inside one coroutine to keep context vars coherent.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import task_graph  # noqa: E402
from orchestrator import skills, task_tracking  # noqa: E402

from tests.test_task_graph import _FakeRedis  # noqa: E402


CONV = "conv-track"
INVOKE_SKILL = skills.invoke_skill


@pytest.fixture()
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    task_tracking._turn.set(None)
    task_tracking._nested_parent.set(None)
    return fake


async def _run_skill(
    conversation_id: str, skill_id: str, result: Dict[str, Any]
) -> None:
    async with task_tracking.track_skill(conversation_id, skill_id) as tracker:
        task_tracking.apply_result_outcome(tracker, result)


def _by_skill(conversation_id: str) -> Dict[str, Any]:
    return {n.skill or "ROOT": n for n in task_graph.list_nodes(conversation_id)}


def test_root_is_lazy_no_dispatch_no_node(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "hello there")
        task_tracking.finish_turn("answer")

    asyncio.run(scenario())
    assert task_graph.list_nodes(CONV) == []


def test_single_skill_creates_root_and_child(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "run corrosion on X")
        await _run_skill(
            CONV,
            "corrosion_analysis",
            {"skill_id": "corrosion_analysis", "result": {"ok": True}},
        )
        task_tracking.finish_turn("completed")

    asyncio.run(scenario())
    nodes = _by_skill(CONV)
    assert "ROOT" in nodes
    assert "corrosion_analysis" in nodes
    assert nodes["corrosion_analysis"].parent_task_id == nodes["ROOT"].task_id
    assert nodes["corrosion_analysis"].state == "completed"
    assert nodes["ROOT"].state == "completed"


def test_failed_skill_marks_child_failed_and_root_fails(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "do thing")
        await _run_skill(CONV, "thermal", {"skill_id": "thermal", "error": "boom"})
        task_tracking.finish_turn("completed")  # fail_fast percolates child failure

    asyncio.run(scenario())
    nodes = _by_skill(CONV)
    assert nodes["thermal"].state == "failed"
    assert nodes["thermal"].error == "boom"
    assert nodes["ROOT"].state == "failed"


def test_input_required_marks_child(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "needs params")
        await _run_skill(
            CONV,
            "data_lookup",
            {"skill_id": "data_lookup", "input_required": {"q": "which?"}},
        )
        task_tracking.finish_turn("needs_info")  # paused → root left non-terminal

    asyncio.run(scenario())
    nodes = _by_skill(CONV)
    assert nodes["data_lookup"].state == "input-required"
    assert nodes["ROOT"].state == "working"


def test_result_ref_extracted_from_artifacts(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "make artifact")
        await _run_skill(
            CONV,
            "synthesis",
            {
                "skill_id": "synthesis",
                "result": {"artifacts": [{"artifact_id": "art-123"}]},
            },
        )
        task_tracking.finish_turn("completed")

    asyncio.run(scenario())
    assert _by_skill(CONV)["synthesis"].result_ref == "art-123"


def test_streaming_skill_status_updates_tracked_node(
    fake_redis: _FakeRedis, monkeypatch
) -> None:
    status_history = []

    class _StreamingTool:
        async def ainvoke(self, params):
            await params["_status_callback"]("Running execute_code… mesh iteration 2")
            return {"message": "done"}

    async def fake_find_tool_for_skill(*_args, **_kwargs):
        return _StreamingTool()

    async def fake_get_capability_by_skill_id(_skill_id):
        return SimpleNamespace(input_schema={}, supports_streaming=True)

    monkeypatch.setattr(skills, "find_tool_for_skill", fake_find_tool_for_skill)
    monkeypatch.setattr(
        skills,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id
        ),
    )
    monkeypatch.setattr(
        skills.runtime,
        "store_status_update",
        lambda _conversation_id, message, **_kwargs: status_history.append(message),
    )

    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "mesh this")
        result = await INVOKE_SKILL("mesh_geometry", {}, CONV)
        assert result["result"] == {"message": "done"}

    asyncio.run(scenario())

    mesh = _by_skill(CONV)["mesh_geometry"]
    assert mesh.last_status_message == "Running execute_code… mesh iteration 2"
    assert "[mesh_geometry] Running execute_code… mesh iteration 2" in status_history


def test_sibling_skills_share_root(fake_redis: _FakeRedis) -> None:
    async def scenario() -> None:
        task_tracking.begin_turn(CONV, "two skills")
        await _run_skill(CONV, "a", {"skill_id": "a", "result": {}})
        await _run_skill(CONV, "b", {"skill_id": "b", "result": {}})
        task_tracking.finish_turn("completed")

    asyncio.run(scenario())
    tree = task_graph.build_tree(CONV)
    assert len(tree) == 1
    assert {c["skill"] for c in tree[0]["children"]} == {"a", "b"}
