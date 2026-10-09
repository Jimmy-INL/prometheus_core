"""Tests for the TEMPLATE_NAME agent's `_execute` logic.

Extend these as you implement your agent: every input-validation branch and
every distinct result shape deserves a test. Run with `uv run pytest`.
"""

from agent import TEMPLATE_CLASSAgent


def _make_agent() -> TEMPLATE_CLASSAgent:
    # agent_card.json is loaded lazily by run()/build_app(), not by the
    # constructor, so unit tests can instantiate the agent directly.
    return TEMPLATE_CLASSAgent(agent_name="TEMPLATE_NAME Agent")


async def test_execute_returns_success_for_valid_input(context, event_queue):
    agent = _make_agent()

    result = await agent._execute({"input_data": "hello"}, context, event_queue)

    assert result["status"] == "success"
    assert result["input_received"] == "hello"
    # The progress update was emitted through the event queue.
    assert event_queue.enqueue_event.await_count >= 1


async def test_execute_rejects_missing_input(context, event_queue):
    agent = _make_agent()

    result = await agent._execute({}, context, event_queue)

    assert result["status"] == "error"
    assert "input_data" in result["error"]
