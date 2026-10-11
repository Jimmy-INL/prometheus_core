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

"""Tests for turn-level backgrounding helpers (deadline, detach, finisher).

All testable logic lives in task_tracking (which depends only on task_graph), so
these tests need neither the orchestrator service nor prometheus_api — keeping
them isolated from the sys.modules stubbing other suites rely on.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

import task_graph  # noqa: E402
from orchestrator import task_tracking  # noqa: E402

from tests.test_task_graph import _FakeRedis  # noqa: E402

CONV = "conv-bg"


@pytest.fixture()
def fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    task_tracking._turn.set(None)
    task_tracking._nested_parent.set(None)
    return fake


# --- env parsing -------------------------------------------------------------


def test_deadline_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", raising=False)
    assert task_tracking.background_deadline_seconds() == 0.0


def test_deadline_parsed(monkeypatch) -> None:
    monkeypatch.setenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", "45")
    assert task_tracking.background_deadline_seconds() == 45.0


def test_deadline_invalid_disables(monkeypatch) -> None:
    monkeypatch.setenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", "nonsense")
    assert task_tracking.background_deadline_seconds() == 0.0


# --- result store + detach helpers ------------------------------------------


def test_store_and_get_result(fake_redis: _FakeRedis) -> None:
    task_graph.store_result(CONV, "root", {"status": "completed", "report": "hi"})
    assert task_graph.get_result(CONV, "root") == {"status": "completed", "report": "hi"}
    assert task_graph.get_result(CONV, "missing") is None


def test_ensure_background_root_materializes_and_flags(fake_redis: _FakeRedis) -> None:
    task_tracking.begin_turn(CONV, "long running thing")
    root_id = task_tracking.ensure_background_root()
    assert root_id is not None
    node = task_graph.get_node(CONV, root_id)
    assert node is not None
    assert node.is_background is True
    assert node.state == "working"


def test_finish_turn_for_completes_root(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="x")
    task_graph.update_own_state(CONV, "root", own_state="working")
    task_tracking.finish_turn_for(CONV, "root", "completed")
    assert task_graph.get_node(CONV, "root").state == "completed"


def test_finish_turn_for_completes_needs_info_root_own_work(fake_redis: _FakeRedis) -> None:
    task_graph.create_node(task_id="root", conversation_id=CONV, title="x")
    task_graph.update_own_state(CONV, "root", own_state="working")
    task_tracking.finish_turn_for(CONV, "root", "needs_info")
    assert task_graph.get_node(CONV, "root").state == "completed"


# --- proactive detach (declare_long_running) ---------------------------------


def test_background_event_none_outside_turn(fake_redis: _FakeRedis) -> None:
    task_tracking._turn.set(None)
    assert task_tracking.background_event() is None


def test_background_event_present_within_turn(fake_redis: _FakeRedis) -> None:
    task_tracking.begin_turn(CONV, "thing")
    evt = task_tracking.background_event()
    assert evt is not None
    assert not evt.is_set()


def test_request_background_sets_event_and_flags_nodes(fake_redis: _FakeRedis) -> None:
    task_tracking.begin_turn(CONV, "thing")
    root_id = task_tracking._ensure_root()
    # Simulate being inside a tracked skill dispatch.
    node_id = "t_child"
    task_graph.create_node(task_id=node_id, conversation_id=CONV, parent_task_id=root_id, title="skill")
    token = task_tracking._nested_parent.set(node_id)
    try:
        task_tracking.request_background()
    finally:
        task_tracking._nested_parent.reset(token)

    assert task_tracking.background_event().is_set()
    assert task_graph.get_node(CONV, node_id).is_background is True
    assert task_graph.get_node(CONV, root_id).is_background is True


def test_request_background_noop_outside_turn(fake_redis: _FakeRedis) -> None:
    task_tracking._turn.set(None)
    task_tracking.request_background()  # must not raise


# --- background finisher -----------------------------------------------------


def test_finisher_completes_root_and_persists_result(fake_redis: _FakeRedis) -> None:
    statuses: list[str] = []

    async def scenario() -> None:
        task_graph.create_node(task_id="root", conversation_id=CONV, title="x")
        task_graph.update_own_state(CONV, "root", own_state="working", is_background=True)

        async def chat_result() -> SimpleNamespace:
            return SimpleNamespace(status="completed", report="all done")

        await task_tracking.run_background_finish(
            chat_task=asyncio.ensure_future(chat_result()),
            conversation_id=CONV,
            root_id="root",
            build_payload=lambda resp: {"status": resp.status, "report": resp.report},
            on_status=statuses.append,
        )

    asyncio.run(scenario())
    assert task_graph.get_node(CONV, "root").state == "completed"
    assert task_graph.get_result(CONV, "root")["report"] == "all done"
    assert statuses == ["Background task complete."]


def test_finisher_marks_root_failed_on_exception(fake_redis: _FakeRedis) -> None:
    statuses: list[str] = []

    async def scenario() -> None:
        task_graph.create_node(task_id="root", conversation_id=CONV, title="x")
        task_graph.update_own_state(CONV, "root", own_state="working", is_background=True)

        async def chat_boom() -> SimpleNamespace:
            raise RuntimeError("kaboom")

        await task_tracking.run_background_finish(
            chat_task=asyncio.ensure_future(chat_boom()),
            conversation_id=CONV,
            root_id="root",
            build_payload=lambda resp: {},
            on_status=statuses.append,
        )

    asyncio.run(scenario())
    node = task_graph.get_node(CONV, "root")
    assert node.state == "failed"
    assert "kaboom" in (node.error or "")
    assert statuses and "kaboom" in statuses[0]
