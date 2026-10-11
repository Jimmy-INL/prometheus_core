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

"""Unit tests for the Task Graph registry and percolation logic.

These exercise ``task_graph._reconcile`` against an in-memory fake Redis so the
percolation algorithm (the core of background-task tracking) is covered without
a running Redis.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import task_graph  # noqa: E402


class _FakePipeline:
    def __init__(self, store: "_FakeRedis") -> None:
        self._store = store

    # Each op applies immediately; execute() is a no-op batch boundary.
    def set(self, key: str, val: str) -> "_FakePipeline":
        self._store.set(key, val)
        return self

    def expire(self, *_args, **_kwargs) -> "_FakePipeline":
        return self

    def sadd(self, key: str, *vals: str) -> "_FakePipeline":
        self._store.sadd(key, *vals)
        return self

    def execute(self) -> List[Any]:
        return []


class _FakeRedis:
    """Just enough of redis-py (decode_responses=True) for the task graph."""

    def __init__(self) -> None:
        self.kv: Dict[str, str] = {}
        self.sets: Dict[str, set] = {}
        self.lists: Dict[str, List[str]] = {}
        self.published: List[tuple[str, str]] = []

    def set(self, key: str, val: str) -> None:
        self.kv[key] = val

    def get(self, key: str):
        return self.kv.get(key)

    def expire(self, *_args, **_kwargs) -> None:
        return None

    def sadd(self, key: str, *vals: str) -> None:
        self.sets.setdefault(key, set()).update(vals)

    def smembers(self, key: str) -> set:
        return set(self.sets.get(key, set()))

    def rpush(self, key: str, *vals: str) -> None:
        self.lists.setdefault(key, []).extend(vals)

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        data = self.lists.get(key, [])
        if end == -1:
            return data[start:]
        return data[start : end + 1]

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


@pytest.fixture()
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    return fake


CONV = "conv-1"


def _events_of_type(fake: _FakeRedis, event_type: str) -> List[Dict[str, Any]]:
    out = []
    for _channel, msg in fake.published:
        event = json.loads(msg)
        if event.get("type") == event_type:
            out.append(event)
    return out


def test_leaf_completion_marks_terminal(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="ask")
    node = task_graph.update_own_state(CONV, "root", own_state="completed")

    assert node is not None
    assert node.state == "completed"
    assert node.finished_at is not None
    assert _events_of_type(fake_redis, "node-completed")


def test_parent_blocked_while_child_runs(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="ask")
    task_graph.create_node(
        task_id="child", conversation_id=CONV, parent_task_id="root", agent="thermal"
    )

    # Child starts working → root should be working and waiting on the child.
    task_graph.update_own_state(CONV, "child", own_state="working", message="step 1/10")
    root = task_graph.get_node(CONV, "root")
    assert root is not None
    assert root.state == "working"
    assert root.waiting_on == ["child"]

    # Root's own work is done, but it stays working until the child finishes.
    task_graph.update_own_state(CONV, "root", own_state="completed")
    root = task_graph.get_node(CONV, "root")
    assert root.state == "working"

    # Child completes → root percolates to completed.
    task_graph.update_own_state(CONV, "child", own_state="completed")
    root = task_graph.get_node(CONV, "root")
    assert root.state == "completed"
    assert root.waiting_on == []


def test_completion_cascades_two_levels(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV)
    task_graph.create_node(
        task_id="synth", conversation_id=CONV, parent_task_id="root", agent="synthesis"
    )
    task_graph.create_node(
        task_id="therm", conversation_id=CONV, parent_task_id="synth", agent="thermal"
    )

    # Both intermediate and root finished their own work; only the deep leaf runs.
    task_graph.update_own_state(CONV, "root", own_state="completed")
    task_graph.update_own_state(CONV, "synth", own_state="completed")
    task_graph.update_own_state(CONV, "therm", own_state="working", message="solving")

    assert task_graph.get_node(CONV, "root").state == "working"
    assert task_graph.get_node(CONV, "synth").state == "working"

    # Deep leaf finishes → cascade all the way to the root.
    task_graph.update_own_state(CONV, "therm", own_state="completed")
    assert task_graph.get_node(CONV, "therm").state == "completed"
    assert task_graph.get_node(CONV, "synth").state == "completed"
    assert task_graph.get_node(CONV, "root").state == "completed"


def test_fail_fast_propagates_child_failure(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, fail_fast=True)
    task_graph.create_node(task_id="child", conversation_id=CONV, parent_task_id="root")

    task_graph.update_own_state(CONV, "root", own_state="completed")
    task_graph.update_own_state(CONV, "child", own_state="failed", error="boom")

    root = task_graph.get_node(CONV, "root")
    assert root.state == "failed"
    assert _events_of_type(fake_redis, "node-failed")


def test_deepest_blocking_message_surfaces_to_root(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV)
    task_graph.create_node(
        task_id="therm",
        conversation_id=CONV,
        parent_task_id="root",
        agent="thermal",
        title="Thermal sim",
    )
    task_graph.update_own_state(CONV, "root", own_state="completed")
    task_graph.update_own_state(
        CONV, "therm", own_state="working", message="step 142/500"
    )

    root = task_graph.get_node(CONV, "root")
    assert "waiting on Thermal sim" in root.last_status_message
    assert "step 142/500" in root.last_status_message


def test_message_only_progress_publishes_and_percolates(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="ask")
    task_graph.create_node(
        task_id="mesh",
        conversation_id=CONV,
        parent_task_id="root",
        title="Cubit mesh",
    )
    task_graph.update_own_state(CONV, "root", own_state="working")
    task_graph.update_own_state(
        CONV,
        "mesh",
        own_state="working",
        message="mesh iteration 1",
        progress=0.1,
    )
    fake_redis.published.clear()

    task_graph.update_own_state(
        CONV,
        "mesh",
        own_state="working",
        message="mesh iteration 2",
        progress=0.2,
    )

    updates = _events_of_type(fake_redis, "node-updated")
    mesh_update = next(event for event in updates if event["task_id"] == "mesh")
    root_update = next(event for event in updates if event["task_id"] == "root")
    assert mesh_update["root_task_id"] == "root"
    assert mesh_update["message"] == "mesh iteration 2"
    assert mesh_update["progress"] == 0.2
    assert "mesh iteration 2" in root_update["message"]
    assert "mesh iteration 2" in task_graph.get_node(CONV, "root").last_status_message

    fake_redis.published.clear()
    task_graph.update_own_state(
        CONV,
        "mesh",
        own_state="working",
        message="mesh iteration 2",
        progress=0.2,
    )
    assert fake_redis.published == []


def test_build_tree_nests_children(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="ask")
    task_graph.create_node(
        task_id="a", conversation_id=CONV, parent_task_id="root", agent="corrosion"
    )
    task_graph.create_node(
        task_id="b", conversation_id=CONV, parent_task_id="root", agent="thermal"
    )

    tree = task_graph.build_tree(CONV)
    assert len(tree) == 1
    root = tree[0]
    assert root["task_id"] == "root"
    child_ids = {c["task_id"] for c in root["children"]}
    assert child_ids == {"a", "b"}
