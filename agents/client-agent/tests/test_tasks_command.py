"""Tests for the /tasks slash command (list + inspect)."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

# Stub the remaining LangChain tool dependency; the /tasks path never touches it.
if "langchain_core.tools" not in sys.modules:
    _tools = types.ModuleType("langchain_core.tools")

    class _StructuredTool:
        @staticmethod
        def from_function(*args, **kwargs):
            return SimpleNamespace(name=kwargs.get("name", "tool"), invoke=lambda a: {})

    _tools.StructuredTool = _StructuredTool
    sys.modules["langchain_core.tools"] = _tools

import task_graph  # noqa: E402
from orchestrator import debug_commands, runtime  # noqa: E402
from orchestrator.models import ConversationRequest  # noqa: E402

from tests.test_task_graph import _FakeRedis  # noqa: E402

CONV = "conv-tasks-cmd"


@pytest.fixture()
def populated(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    monkeypatch.setattr(runtime, "store_status_update", lambda *a, **k: None)

    # root → corrosion (done) + thermal (still working)
    task_graph.create_node(task_id="root", conversation_id=CONV, title="analyze assembly-7")
    task_graph.update_own_state(CONV, "root", own_state="working")
    task_graph.create_node(task_id="corr", conversation_id=CONV, parent_task_id="root", agent="corrosion", skill="corrosion_rate")
    task_graph.update_own_state(CONV, "corr", own_state="completed")
    task_graph.create_node(task_id="therm", conversation_id=CONV, parent_task_id="root", agent="thermal", skill="thermal_sim", title="Thermal sim")
    task_graph.update_own_state(CONV, "therm", own_state="working", message="step 142/500")
    return fake


def _handle(query: str):
    return asyncio.run(
        debug_commands._maybe_handle_slash_command(
            ConversationRequest(query=query, conversation_id=CONV), CONV, None, []
        )
    )


def test_tasks_list_renders_tree(populated: _FakeRedis) -> None:
    response = _handle("/tasks")
    assert response is not None
    assert response.status == "answer"
    assert response.message_metadata["slash_command"] == "tasks"
    msg = response.message
    assert "Tasks (1 total, 1 active)" in msg
    assert "analyze assembly-7" in msg
    assert "corrosion_rate" in msg
    assert "Thermal sim" in msg
    assert "step 142/500" in msg  # working node surfaces its status
    assert "```text\n" in msg
    assert "\n  └─ " in msg
    assert "\n```\n\nUse `/tasks <id>`" in msg
    # structured tree is attached for richer rendering
    assert isinstance(response.message_metadata["tasks"], list)
    assert response.message_metadata["tasks"][0]["task_id"] == "root"


def test_tasks_detail_by_id(populated: _FakeRedis) -> None:
    response = _handle("/tasks therm")
    assert response is not None
    assert "Task therm" in response.message
    assert "thermal" in response.message
    assert "step 142/500" in response.message
    assert response.message.startswith("Task therm\n\n```text\n")
    assert "\n  state:   working\n" in response.message
    assert response.message.endswith("\n```")
    assert response.message_metadata["task_id"] == "therm"


def test_tasks_detail_accepts_id_prefix(populated: _FakeRedis) -> None:
    # 'cor' is a prefix of 'corr'
    response = _handle("/tasks cor")
    assert response is not None
    assert "Task corr" in response.message


def test_tasks_detail_unknown_id(populated: _FakeRedis) -> None:
    response = _handle("/tasks nope")
    assert response is not None
    assert "No task found" in response.message


def test_tasks_empty(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    monkeypatch.setattr(runtime, "store_status_update", lambda *a, **k: None)
    response = _handle("/tasks")
    assert response is not None
    assert "No tasks have run" in response.message


def test_unknown_command_lists_tasks(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(task_graph, "_client", lambda: fake)
    monkeypatch.setattr(runtime, "store_status_update", lambda *a, **k: None)
    response = _handle("/bogus")
    assert response is not None
    assert "/tasks" in response.message
    assert "tasks" in response.message_metadata["supported_commands"]
