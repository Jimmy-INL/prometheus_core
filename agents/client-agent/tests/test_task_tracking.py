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
        task_tracking.finish_turn("needs_info")

    asyncio.run(scenario())
    nodes = _by_skill(CONV)
    assert nodes["data_lookup"].state == "input-required"
    assert nodes["ROOT"].own_state == "completed"
    assert nodes["ROOT"].state == "working"


def test_input_required_resume_reuses_root_and_child(fake_redis: _FakeRedis) -> None:
    async def scenario() -> tuple[str, str]:
        task_tracking.begin_turn(CONV, "create a valve")
        async with task_tracking.track_skill(
            CONV, "author_equipment_geometry"
        ) as tracker:
            root_id = task_tracking.current_root_id()
            node_id = tracker.node_id
            tracker.input_required()
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "rod diameter is 5 cm")
        async with task_tracking.track_skill(
            CONV,
            "author_equipment_geometry",
            resume_node_id=node_id,
            resume_root_id=root_id,
        ) as resumed:
            assert resumed.node_id == node_id
            resumed.complete()
        task_tracking.finish_turn("completed")
        return root_id, node_id

    root_id, node_id = asyncio.run(scenario())
    nodes = task_graph.list_nodes(CONV)
    tree = task_graph.build_tree(CONV)

    assert len(nodes) == 2
    assert len(tree) == 1
    assert tree[0]["task_id"] == root_id
    assert tree[0]["state"] == "completed"
    assert tree[0]["children"][0]["task_id"] == node_id
    assert tree[0]["children"][0]["state"] == "completed"


def test_repeated_input_required_resume_reuses_same_nodes(
    fake_redis: _FakeRedis,
) -> None:
    async def scenario() -> tuple[str, str]:
        task_tracking.begin_turn(CONV, "create a valve")
        async with task_tracking.track_skill(
            CONV, "author_equipment_geometry"
        ) as tracker:
            root_id = task_tracking.current_root_id()
            node_id = tracker.node_id
            tracker.input_required()
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "the rod is steel")
        async with task_tracking.track_skill(
            CONV,
            "author_equipment_geometry",
            resume_node_id=node_id,
            resume_root_id=root_id,
        ) as resumed:
            resumed.input_required()
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "the diameter is 5 cm")
        async with task_tracking.track_skill(
            CONV,
            "author_equipment_geometry",
            resume_node_id=node_id,
            resume_root_id=root_id,
        ) as resumed:
            resumed.complete()
        task_tracking.finish_turn("completed")
        return root_id, node_id

    root_id, node_id = asyncio.run(scenario())
    nodes = task_graph.list_nodes(CONV)

    assert {node.task_id for node in nodes} == {root_id, node_id}
    assert task_graph.get_node(CONV, root_id).state == "completed"
    assert task_graph.get_node(CONV, node_id).state == "completed"


def test_multiple_input_required_children_resume_under_original_root(
    fake_redis: _FakeRedis,
) -> None:
    async def scenario() -> tuple[str, set[str]]:
        task_tracking.begin_turn(CONV, "run two analyses")
        nodes_by_skill: dict[str, str] = {}
        for skill_id in ("thermal", "corrosion"):
            async with task_tracking.track_skill(CONV, skill_id) as tracker:
                nodes_by_skill[skill_id] = tracker.node_id
                tracker.input_required()
        root_id = task_tracking.current_root_id()
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "here are both values")
        for skill_id, node_id in nodes_by_skill.items():
            async with task_tracking.track_skill(
                CONV,
                skill_id,
                resume_node_id=node_id,
                resume_root_id=root_id,
            ) as resumed:
                resumed.complete()
        task_tracking.finish_turn("completed")
        return root_id, set(nodes_by_skill.values())

    root_id, node_ids = asyncio.run(scenario())
    nodes = task_graph.list_nodes(CONV)

    assert {node.task_id for node in nodes} == {root_id, *node_ids}
    assert task_graph.get_node(CONV, root_id).state == "completed"
    assert all(task_graph.get_node(CONV, node_id).state == "completed" for node_id in node_ids)


def test_input_required_resume_failure_fails_original_tree(
    fake_redis: _FakeRedis,
) -> None:
    async def scenario() -> tuple[str, str]:
        task_tracking.begin_turn(CONV, "create a valve")
        async with task_tracking.track_skill(
            CONV, "author_equipment_geometry"
        ) as tracker:
            root_id = task_tracking.current_root_id()
            node_id = tracker.node_id
            tracker.input_required()
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "rod diameter is 5 cm")
        with pytest.raises(RuntimeError, match="resume failed"):
            async with task_tracking.track_skill(
                CONV,
                "author_equipment_geometry",
                resume_node_id=node_id,
                resume_root_id=root_id,
            ):
                raise RuntimeError("resume failed")
        task_tracking.finish_turn("error")
        return root_id, node_id

    root_id, node_id = asyncio.run(scenario())
    nodes = task_graph.list_nodes(CONV)

    assert {node.task_id for node in nodes} == {root_id, node_id}
    assert task_graph.get_node(CONV, node_id).state == "failed"
    assert task_graph.get_node(CONV, root_id).state == "failed"


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


def test_invoke_skill_returns_and_consumes_task_graph_resume_ids(
    fake_redis: _FakeRedis, monkeypatch
) -> None:
    invoked_params: list[Dict[str, Any]] = []

    class _InputRequiredThenCompleteTool:
        async def ainvoke(self, params):
            invoked_params.append(params)
            if len(invoked_params) == 1:
                return {
                    "status": "input_required",
                    "input_required": {
                        "missing_inputs": [{"name": "rod_diameter", "type": "number"}]
                    },
                    "_a2a_context_id": "a2a-context-1",
                    "_a2a_task_id": "a2a-task-1",
                }
            return {"message": "done"}

    tool = _InputRequiredThenCompleteTool()

    async def fake_find_tool_for_skill(*_args, **_kwargs):
        return tool

    async def fake_get_capability_by_skill_id(_skill_id):
        return None

    monkeypatch.setattr(skills, "find_tool_for_skill", fake_find_tool_for_skill)
    monkeypatch.setattr(
        skills,
        "get_capability_cache",
        lambda: SimpleNamespace(
            get_capability_by_skill_id=fake_get_capability_by_skill_id
        ),
    )
    monkeypatch.setattr(skills.runtime, "store_status_update", lambda *_args, **_kwargs: None)

    async def scenario() -> tuple[str, str]:
        task_tracking.begin_turn(CONV, "create a valve")
        pending = await INVOKE_SKILL("author_equipment_geometry", {}, CONV)
        root_id = pending["_task_graph_root_id"]
        node_id = pending["_task_graph_node_id"]
        task_tracking.finish_turn("needs_info")

        task_tracking.begin_turn(CONV, "rod diameter is 5 cm")
        result = await INVOKE_SKILL(
            "author_equipment_geometry",
            {
                "provided_inputs": {"rod_diameter": 0.05},
                "_a2a_context_id": pending["_a2a_context_id"],
                "_a2a_task_id": pending["_a2a_task_id"],
                "_task_graph_root_id": root_id,
                "_task_graph_node_id": node_id,
            },
            CONV,
        )
        assert result["result"] == {"message": "done"}
        task_tracking.finish_turn("completed")
        return root_id, node_id

    root_id, node_id = asyncio.run(scenario())

    assert all("_task_graph_root_id" not in params for params in invoked_params)
    assert all("_task_graph_node_id" not in params for params in invoked_params)
    assert {node.task_id for node in task_graph.list_nodes(CONV)} == {root_id, node_id}


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
