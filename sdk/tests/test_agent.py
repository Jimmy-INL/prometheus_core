"""Tests for the agent module."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from prometheus_api.agent import (
    PrometheusAgent,
    PrometheusAgentExecutor,
    RequestContext,
    EventQueue,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)


class TestPrometheusAgentExecutor:
    """Tests for PrometheusAgentExecutor."""

    @pytest.fixture
    def executor(self):
        """Create a test executor."""
        return PrometheusAgentExecutor(agent_name="TestAgent")

    @pytest.fixture
    def mock_context(self):
        """Create a mock RequestContext."""
        context = MagicMock(spec=RequestContext)
        context.task_id = "test-task-123"
        context.context_id = "test-context-456"
        context.get_user_input.return_value = '{"input": "test data"}'
        return context

    @pytest.fixture
    def mock_event_queue(self):
        """Create a mock EventQueue."""
        queue = AsyncMock(spec=EventQueue)
        return queue

    def test_executor_initialization(self, executor):
        """Test executor initializes with correct name."""
        assert executor.agent_name == "TestAgent"

    def test_extract_params_json(self, executor):
        """Test parameter extraction from JSON input."""
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = '{"key": "value", "number": 42}'

        params = executor._extract_params(context)

        assert params == {"key": "value", "number": 42}

    def test_extract_params_empty(self, executor):
        """Test parameter extraction with empty input."""
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = ""

        params = executor._extract_params(context)

        assert params == {}

    def test_extract_params_plain_text(self, executor):
        """Test parameter extraction with non-JSON text."""
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = "Hello, this is plain text"

        params = executor._extract_params(context)

        assert params == {"message": "Hello, this is plain text"}

    @pytest.mark.asyncio
    async def test_execute_calls_enqueue_event(self, executor, mock_context, mock_event_queue):
        """Test that execute uses enqueue_event for status updates."""

        # Create a concrete implementation for testing
        class TestExecutor(PrometheusAgentExecutor):
            async def process_analysis(self, params, context, event_queue):
                return {"status": "success", "data": params.get("input")}

        test_executor = TestExecutor(agent_name="TestAgent")

        await test_executor.execute(mock_context, mock_event_queue)

        # Verify enqueue_event was called (not put)
        assert mock_event_queue.enqueue_event.called
        calls = mock_event_queue.enqueue_event.call_args_list

        # Should have at least 3 calls: working status, completed status, artifact
        assert len(calls) >= 3

        # Check first call is working status
        first_event = calls[0][0][0]
        assert isinstance(first_event, TaskStatusUpdateEvent)
        assert first_event.status.state == TaskState.working
        assert first_event.task_id == "test-task-123"
        assert first_event.context_id == "test-context-456"

        # Check second call is completed status
        second_event = calls[1][0][0]
        assert isinstance(second_event, TaskStatusUpdateEvent)
        assert second_event.status.state == TaskState.completed
        assert second_event.final is True

        # Check third call is artifact
        third_event = calls[2][0][0]
        assert isinstance(third_event, TaskArtifactUpdateEvent)
        assert third_event.task_id == "test-task-123"

    @pytest.mark.asyncio
    async def test_execute_handles_errors(self, executor, mock_context, mock_event_queue):
        """Test that execute sends failed status on error."""

        class FailingExecutor(PrometheusAgentExecutor):
            async def process_analysis(self, params, context, event_queue):
                raise ValueError("Test error")

        test_executor = FailingExecutor(agent_name="TestAgent")

        with pytest.raises(ValueError, match="Test error"):
            await test_executor.execute(mock_context, mock_event_queue)

        # Should have sent working status, then failed status
        calls = mock_event_queue.enqueue_event.call_args_list
        assert len(calls) >= 2

        # Last call should be failed status
        last_event = calls[-1][0][0]
        assert isinstance(last_event, TaskStatusUpdateEvent)
        assert last_event.status.state == TaskState.failed

    @pytest.mark.asyncio
    async def test_cancel_sends_canceled_status(self, executor, mock_context, mock_event_queue):
        """Test that cancel sends canceled status."""
        await executor.cancel(mock_context, mock_event_queue)

        mock_event_queue.enqueue_event.assert_called_once()
        event = mock_event_queue.enqueue_event.call_args[0][0]

        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.canceled
        assert event.task_id == "test-task-123"
        assert event.context_id == "test-context-456"
        assert event.final is True

    @pytest.mark.asyncio
    async def test_process_analysis_not_implemented(self, executor, mock_context, mock_event_queue):
        """Test that base executor raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await executor.process_analysis({}, mock_context, mock_event_queue)


class TestPrometheusAgent:
    """Tests for PrometheusAgent."""

    def test_agent_initialization(self):
        """Test agent initializes with default values."""
        agent = PrometheusAgent(agent_name="MyAgent")

        assert agent.agent_name == "MyAgent"
        assert agent.agent_card_path == "agent_card.json"
        assert agent.agent_card is None
        assert agent.executor is None

    def test_agent_custom_card_path(self):
        """Test agent accepts custom card path."""
        agent = PrometheusAgent(
            agent_name="MyAgent",
            agent_card_path="/custom/path/card.json"
        )

        assert agent.agent_card_path == "/custom/path/card.json"

    @pytest.mark.asyncio
    async def test_agent_process_analysis_not_implemented(self):
        """Test that base agent raises NotImplementedError for process_analysis."""
        agent = PrometheusAgent(agent_name="MyAgent")

        mock_context = MagicMock(spec=RequestContext)
        mock_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(NotImplementedError):
            await agent.process_analysis({}, mock_context, mock_queue)

    def test_create_executor_returns_custom_executor(self):
        """Test that create_executor returns a working executor."""

        class TestAgent(PrometheusAgent):
            async def process_analysis(self, params, context, event_queue):
                return {"result": "test"}

        agent = TestAgent(agent_name="TestAgent")
        executor = agent.create_executor()

        assert isinstance(executor, PrometheusAgentExecutor)
        assert executor.agent_name == "TestAgent"


class TestEventTypes:
    """Tests for A2A event type creation."""

    def test_task_status_update_event_creation(self):
        """Test creating TaskStatusUpdateEvent."""
        event = TaskStatusUpdateEvent(
            taskId="task-123",
            contextId="context-456",
            final=False,
            status=TaskStatus(state=TaskState.working),
        )

        assert event.task_id == "task-123"
        assert event.context_id == "context-456"
        assert event.final is False
        assert event.status.state == TaskState.working

    def test_task_status_states(self):
        """Test all task states are accessible."""
        states = [
            TaskState.submitted,
            TaskState.working,
            TaskState.completed,
            TaskState.canceled,
            TaskState.failed,
        ]

        for state in states:
            status = TaskStatus(state=state)
            assert status.state == state


class TestAgentIntegration:
    """Integration tests for agent components."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Test complete execution flow with a concrete agent."""

        class EchoAgent(PrometheusAgent):
            async def process_analysis(self, params, context, event_queue):
                # Echo the input back
                return {
                    "echo": params.get("message", "no message"),
                    "task_id": context.task_id,
                }

        agent = EchoAgent(agent_name="EchoAgent")
        executor = agent.create_executor()

        # Create mock context and queue
        context = MagicMock(spec=RequestContext)
        context.task_id = "echo-task-1"
        context.context_id = "echo-context-1"
        context.get_user_input.return_value = '{"message": "Hello, World!"}'

        queue = AsyncMock(spec=EventQueue)

        # Execute
        await executor.execute(context, queue)

        # Verify the flow
        calls = queue.enqueue_event.call_args_list

        # Working status
        assert calls[0][0][0].status.state == TaskState.working

        # Completed status
        assert calls[1][0][0].status.state == TaskState.completed

        # Artifact with result
        artifact_event = calls[2][0][0]
        assert isinstance(artifact_event, TaskArtifactUpdateEvent)
        # The parts are TextPart objects with a 'text' attribute
        part = artifact_event.artifact.parts[0]
        # Access the text content (may need to access root for union types)
        text_content = part.text if hasattr(part, 'text') else part.root.text
        result = json.loads(text_content)
        assert result["echo"] == "Hello, World!"
        assert result["task_id"] == "echo-task-1"
