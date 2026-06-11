"""Tests for RedisTaskStore.

These run against the in-memory fallback path (forced via an unreachable Redis
URL, mirroring tests/test_artifacts.py), so they validate the save/get/delete
round-trip and Task (de)serialization without a live Redis.
"""

from __future__ import annotations

import pytest

from a2a.types import Task, TaskState, TaskStatus

from prometheus_api.agent.task_store import TERMINAL_STATES, RedisTaskStore

# Unreachable port → redis_client returns None → memory fallback is exercised.
UNREACHABLE = "redis://localhost:0"


def _task(task_id: str, state: TaskState = TaskState.working) -> Task:
    return Task(
        id=task_id,
        contextId="conv-1",
        status=TaskStatus(state=state),
        kind="task",
    )


@pytest.fixture()
def store() -> RedisTaskStore:
    return RedisTaskStore(redis_url=UNREACHABLE, ttl_seconds=60)


async def test_save_then_get_roundtrips(store: RedisTaskStore) -> None:
    task = _task("t-1")
    await store.save(task)

    loaded = await store.get("t-1")
    assert loaded is not None
    assert loaded.id == "t-1"
    assert loaded.context_id == "conv-1"
    assert loaded.status.state == TaskState.working


async def test_get_missing_returns_none(store: RedisTaskStore) -> None:
    assert await store.get("does-not-exist") is None


async def test_save_overwrites(store: RedisTaskStore) -> None:
    await store.save(_task("t-2", TaskState.submitted))
    await store.save(_task("t-2", TaskState.completed))

    loaded = await store.get("t-2")
    assert loaded is not None
    assert loaded.status.state == TaskState.completed


async def test_delete_removes(store: RedisTaskStore) -> None:
    await store.save(_task("t-3"))
    await store.delete("t-3")
    assert await store.get("t-3") is None
    # Deleting a nonexistent task is a no-op, not an error.
    await store.delete("t-3")


async def test_corrupt_payload_returns_none(store: RedisTaskStore) -> None:
    # Inject a non-Task JSON blob directly into the memory fallback.
    store._memory_store["t-bad"] = '{"not": "a task"}'
    assert await store.get("t-bad") is None


def test_terminal_states_set() -> None:
    assert TaskState.completed in TERMINAL_STATES
    assert TaskState.failed in TERMINAL_STATES
    assert TaskState.canceled in TERMINAL_STATES
    assert TaskState.rejected in TERMINAL_STATES
    assert TaskState.working not in TERMINAL_STATES
