"""Tests for thermal agent INPUT_REQUIRED behavior."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskStatusUpdateEvent

THERMAL_DIR = Path(__file__).resolve().parents[1]
PROMETHEUS_API_DIR = Path(__file__).resolve().parents[3] / "prometheus_api"
if str(PROMETHEUS_API_DIR) not in sys.path:
    sys.path.insert(0, str(PROMETHEUS_API_DIR))

_SPEC = importlib.util.spec_from_file_location("thermal_agent_module", THERMAL_DIR / "agent.py")
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ThermalAnalysisAgent = _MODULE.ThermalAnalysisAgent
from prometheus_api.agent.a2a_utils import TASK_STATE_INPUT_REQUIRED, extract_part_data


def test_thermal_agent_requests_temperature_and_persists_context_state():
    agent = ThermalAnalysisAgent(agent_name="Thermal Analysis Agent")
    context = MagicMock(spec=RequestContext)
    context.task_id = "task-1"
    context.context_id = "ctx-1"
    context.message = MagicMock(parts=[])
    queue = AsyncMock(spec=EventQueue)

    result = asyncio.run(agent._execute({"material_id": "SS316"}, context, queue))

    assert result == {"status": "input_required"}
    calls = queue.enqueue_event.call_args_list
    assert len(calls) == 1
    event = calls[0][0][0]
    assert isinstance(event, TaskStatusUpdateEvent)
    assert event.status.state == TASK_STATE_INPUT_REQUIRED
    payload = extract_part_data(event.status.message.parts[0])
    assert payload["missing_inputs"][0]["name"] == "temperature_c"

    saved = agent.load_context_state("ctx-1")
    assert saved["resolved"]["material_id"] == "SS316"
    assert saved["pending"] == ["temperature_c"]
