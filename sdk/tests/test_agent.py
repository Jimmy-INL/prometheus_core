"""Tests for the agent module."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.applications import Starlette

from prometheus_api.agent import (
    DelegatingPrometheusAgentExecutor,
    MissingInput,
    PrometheusAgent,
    PrometheusAgentExecutor,
    PrometheusWorker,
    RequestContext,
    EventQueue,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
from prometheus_api.agent.registry import AgentRegistryClient
from prometheus_api.llm_client import AsyncLLMClient, LLMConfig
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Artifact, DataPart, TextPart


def _test_agent_card() -> AgentCard:
    return AgentCard(
        name="Test Agent",
        description="Agent card used by tests",
        url="http://test-agent:8000",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="test_skill",
                name="Test Skill",
                description="Skill used by tests",
                tags=["test"],
            )
        ],
        default_input_modes=["text"],
        default_output_modes=["text"],
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

    def test_extract_params_wraps_json_non_objects(self, executor):
        """JSON values that are not objects should still produce a params dict."""
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = '["alpha", "beta"]'

        params = executor._extract_params(context)

        assert params == {"value": ["alpha", "beta"]}

    def test_extract_params_logs_keys_without_values(self, executor, caplog):
        """Parameter logging should not expose prompt or credential values."""
        context = MagicMock(spec=RequestContext)
        context.get_user_input.return_value = json.dumps(
            {
                "prompt": "sensitive prompt text",
                "llm_api_key": "secret-key",
            }
        )

        with caplog.at_level(logging.INFO):
            params = executor._extract_params(context)

        assert params["llm_api_key"] == "secret-key"
        assert "llm_api_key" in caplog.text
        assert "secret-key" not in caplog.text
        assert "sensitive prompt text" not in caplog.text

    def test_extract_params_without_message_context(self, executor):
        """_extract_params should tolerate local/debug contexts without .message."""

        class LocalLikeContext:
            def get_user_input(self):
                return '{"skill_id": "demo_skill", "message": "hello"}'

        params = executor._extract_params(LocalLikeContext())

        assert params == {"skill_id": "demo_skill", "message": "hello"}

    def test_execute_calls_enqueue_event(self, executor, mock_context, mock_event_queue):
        """Test that execute uses enqueue_event for status updates."""

        # Create a concrete implementation for testing
        class TestExecutor(PrometheusAgentExecutor):
            async def _execute(self, params, context, event_queue):
                return {"status": "success", "data": params.get("input")}

        test_executor = TestExecutor(agent_name="TestAgent")

        asyncio.run(test_executor.execute(mock_context, mock_event_queue))

        # Verify enqueue_event was called (not put)
        assert mock_event_queue.enqueue_event.called
        calls = mock_event_queue.enqueue_event.call_args_list

        # Should have working status then final completed status with the result payload.
        assert len(calls) == 2

        # Check first call is working status
        first_event = calls[0][0][0]
        assert isinstance(first_event, TaskStatusUpdateEvent)
        assert first_event.status.state == TaskState.working
        assert first_event.task_id == "test-task-123"
        assert first_event.context_id == "test-context-456"

        # Check second call is completed status with the final response payload
        second_event = calls[1][0][0]
        assert isinstance(second_event, TaskStatusUpdateEvent)
        assert second_event.status.state == TaskState.completed
        assert second_event.final is True
        payload_text = second_event.status.message.parts[0].root.text
        assert json.loads(payload_text) == {"status": "success", "data": "test data"}

    def test_execute_emits_heartbeats_during_long_execute(self, mock_context, monkeypatch):
        """A slow _execute should produce periodic non-final keepalive events."""
        monkeypatch.setenv("PROMETHEUS_HEARTBEAT_INTERVAL", "0.01")

        events: list = []

        class RecordingQueue:
            async def enqueue_event(self, event):
                events.append(event)

        def _heartbeats():
            return [
                e
                for e in events
                if isinstance(e, TaskStatusUpdateEvent) and (e.metadata or {}).get("heartbeat")
            ]

        class SlowExecutor(PrometheusAgentExecutor):
            async def _execute(self, params, context, event_queue):
                # Wait until at least one keepalive has been emitted, then finish.
                for _ in range(500):
                    if _heartbeats():
                        break
                    await asyncio.sleep(0.01)
                return {"status": "success"}

        asyncio.run(SlowExecutor(agent_name="HB").execute(mock_context, RecordingQueue()))

        heartbeats = _heartbeats()
        assert heartbeats, "expected at least one heartbeat keepalive event"
        for hb in heartbeats:
            assert hb.final is False
            assert hb.status.state == TaskState.working
            assert hb.status.message is None  # silent: no UI text

        # The terminal event is the completed status, emitted after heartbeats stop.
        assert isinstance(events[-1], TaskStatusUpdateEvent)
        assert events[-1].final is True
        assert events[-1].status.state == TaskState.completed
        assert not (events[-1].metadata or {}).get("heartbeat")

    def test_heartbeat_interval_rejects_invalid_values(self, monkeypatch):
        """A non-positive or non-numeric PROMETHEUS_HEARTBEAT_INTERVAL is rejected
        (fail-fast) instead of silently defaulting or disabling the keepalive.
        Heartbeats cannot be turned off, so 0/negative are invalid."""
        for bad in ("0", "-5", "abc"):
            monkeypatch.setenv("PROMETHEUS_HEARTBEAT_INTERVAL", bad)
            with pytest.raises(ValueError):
                PrometheusAgentExecutor._heartbeat_interval()

    def test_heartbeat_interval_defaults_to_15(self, monkeypatch):
        """With the env var unset the interval falls back to the 15 s default."""
        monkeypatch.delenv("PROMETHEUS_HEARTBEAT_INTERVAL", raising=False)
        assert PrometheusAgentExecutor._heartbeat_interval() == 15.0

    def test_execute_handles_errors(self, executor, mock_context, mock_event_queue):
        """Test that execute sends failed status on error."""

        class FailingExecutor(PrometheusAgentExecutor):
            async def _execute(self, params, context, event_queue):
                raise ValueError("Test error")

        test_executor = FailingExecutor(agent_name="TestAgent")

        with pytest.raises(ValueError, match="Test error"):
            asyncio.run(test_executor.execute(mock_context, mock_event_queue))

        # Should have sent working status, then failed status
        calls = mock_event_queue.enqueue_event.call_args_list
        assert len(calls) >= 2

        # Last call should be failed status
        last_event = calls[-1][0][0]
        assert isinstance(last_event, TaskStatusUpdateEvent)
        assert last_event.status.state == TaskState.failed

    def test_execute_skips_auto_finalization_when_agent_finalizes(
        self, mock_context, mock_event_queue
    ):
        """If _execute emits final status, executor should not emit extra terminal events."""

        class FinalizingExecutor(PrometheusAgentExecutor):
            async def _execute(self, params, context, event_queue):
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        taskId=context.task_id,
                        contextId=context.context_id,
                        final=True,
                        status=TaskStatus(state=TaskState.completed),
                    )
                )
                return {"status": "handled-by-agent"}

        test_executor = FinalizingExecutor(agent_name="TestAgent")
        asyncio.run(test_executor.execute(mock_context, mock_event_queue))

        calls = mock_event_queue.enqueue_event.call_args_list
        assert len(calls) == 2

        first_event = calls[0][0][0]
        assert isinstance(first_event, TaskStatusUpdateEvent)
        assert first_event.status.state == TaskState.working
        assert first_event.final is False

        second_event = calls[1][0][0]
        assert isinstance(second_event, TaskStatusUpdateEvent)
        assert second_event.status.state == TaskState.completed
        assert second_event.final is True

    def test_execute_allows_streamed_artifacts_without_adding_extra_result_artifact(
        self, mock_context, mock_event_queue
    ):
        """If _execute emits artifacts, executor should still finalize via status.message only."""

        class ArtifactStreamingExecutor(PrometheusAgentExecutor):
            async def _execute(self, params, context, event_queue):
                await event_queue.enqueue_event(
                    TaskArtifactUpdateEvent(
                        taskId=context.task_id,
                        contextId=context.context_id,
                        artifact=Artifact(
                            artifactId="streamed-artifact",
                            name="progress",
                            parts=[TextPart(text='{"partial": true}')],
                        ),
                    )
                )
                return {"status": "done"}

        test_executor = ArtifactStreamingExecutor(agent_name="TestAgent")
        asyncio.run(test_executor.execute(mock_context, mock_event_queue))

        calls = mock_event_queue.enqueue_event.call_args_list
        artifact_events = [
            call[0][0] for call in calls if type(call[0][0]).__name__ == "TaskArtifactUpdateEvent"
        ]
        completed_events = [
            call[0][0]
            for call in calls
            if isinstance(call[0][0], TaskStatusUpdateEvent)
            and call[0][0].status.state == TaskState.completed
            and call[0][0].final is True
        ]

        assert len(artifact_events) == 1
        assert artifact_events[0].artifact.artifact_id == "streamed-artifact"
        assert len(completed_events) == 1
        payload_text = completed_events[0].status.message.parts[0].root.text
        assert json.loads(payload_text) == {"status": "done"}

    def test_cancel_sends_canceled_status(self, executor, mock_context, mock_event_queue):
        """Test that cancel sends canceled status."""
        asyncio.run(executor.cancel(mock_context, mock_event_queue))

        mock_event_queue.enqueue_event.assert_called_once()
        event = mock_event_queue.enqueue_event.call_args[0][0]

        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.canceled
        assert event.task_id == "test-task-123"
        assert event.context_id == "test-context-456"
        assert event.final is True

    def test__execute_not_implemented(self, executor, mock_context, mock_event_queue):
        """Test that base executor raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            asyncio.run(executor._execute({}, mock_context, mock_event_queue))


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
        agent = PrometheusAgent(agent_name="MyAgent", agent_card_path="/custom/path/card.json")

        assert agent.agent_card_path == "/custom/path/card.json"

    def test_registry_url_defaults_and_strips_env(self, monkeypatch):
        """Test registry URL helper centralizes env lookup and the default value."""
        monkeypatch.delenv("REGISTRY_URL", raising=False)
        assert PrometheusAgent.registry_url() == "http://litellm:4000"

        monkeypatch.setenv("REGISTRY_URL", " http://registry:4000 ")
        assert PrometheusAgent.registry_url() == "http://registry:4000"

    def test_register_with_registry_retries_fallback_url_without_registry_url(self, monkeypatch):
        """Unset REGISTRY_URL still retries the built-in LiteLLM service fallback."""
        agent = PrometheusAgent(agent_name="MyAgent")
        attempts = []
        sleep_delays = []

        class DummyAgentCard:
            name = "My Agent"

        def fail_then_succeed(self, agent_card, *, raw_agent_card=None):
            attempts.append((self.registry_url, self.headers))
            if len(attempts) < 3:
                raise RuntimeError("registry unavailable")

        monkeypatch.delenv("REGISTRY_URL", raising=False)
        monkeypatch.delenv("REGISTRY_MAX_RETRIES", raising=False)
        monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
        monkeypatch.setattr(AgentRegistryClient, "register_once", fail_then_succeed)
        monkeypatch.setattr("prometheus_api.agent.registry.time.sleep", sleep_delays.append)

        agent.register_with_registry(DummyAgentCard())

        assert attempts == [
            ("http://litellm:4000", {}),
            ("http://litellm:4000", {}),
            ("http://litellm:4000", {}),
        ]
        assert sleep_delays == [2.0, 4.0]

    def test_register_with_registry_retries_configured_registry(self, monkeypatch):
        """Explicit registry configuration should use the configured retry count."""
        agent = PrometheusAgent(agent_name="MyAgent")
        attempts = []
        sleep_delays = []

        class DummyAgentCard:
            name = "My Agent"

        def fail_registration(self, agent_card, *, raw_agent_card=None):
            attempts.append((self.registry_url, dict(self.headers)))
            raise RuntimeError("registry unavailable")

        monkeypatch.setenv("REGISTRY_URL", " http://registry:4000 ")
        monkeypatch.setenv("REGISTRY_MAX_RETRIES", "2")
        monkeypatch.setenv("LITELLM_MASTER_KEY", "master-key")
        monkeypatch.setattr(AgentRegistryClient, "register_once", fail_registration)
        monkeypatch.setattr("prometheus_api.agent.registry.time.sleep", sleep_delays.append)

        agent.register_with_registry(
            DummyAgentCard(),
            initial_delay=0.5,
            max_delay=0.75,
            backoff_factor=2.0,
        )

        assert attempts == [
            ("http://registry:4000", {"Authorization": "Bearer master-key"}),
            ("http://registry:4000", {"Authorization": "Bearer master-key"}),
            ("http://registry:4000", {"Authorization": "Bearer master-key"}),
        ]
        assert sleep_delays == [0.5, 0.75]

    def test_register_with_registry_ignores_invalid_retry_env(self, monkeypatch, caplog):
        """Bad REGISTRY_MAX_RETRIES should not prevent agent startup."""
        agent = PrometheusAgent(agent_name="MyAgent")
        attempts = []
        sleep_delays = []

        class DummyAgentCard:
            name = "My Agent"

        def fail_then_succeed(self, agent_card, *, raw_agent_card=None):
            attempts.append(self.registry_url)
            if len(attempts) < 3:
                raise RuntimeError("registry unavailable")

        monkeypatch.delenv("REGISTRY_URL", raising=False)
        monkeypatch.setenv("REGISTRY_MAX_RETRIES", "not-an-int")
        monkeypatch.setattr(AgentRegistryClient, "register_once", fail_then_succeed)
        monkeypatch.setattr("prometheus_api.agent.registry.time.sleep", sleep_delays.append)

        with caplog.at_level(logging.WARNING):
            agent.register_with_registry(DummyAgentCard())

        assert attempts == [
            "http://litellm:4000",
            "http://litellm:4000",
            "http://litellm:4000",
        ]
        assert sleep_delays == [2.0, 4.0]
        assert "Invalid REGISTRY_MAX_RETRIES='not-an-int'; using 10" in caplog.text

    def test_registry_client_build_payload_uses_raw_card_and_agent_secret(self):
        """Registry payload should preserve raw card metadata and static auth headers."""
        raw_agent_card = {
            "name": "Test Agent",
            "description": "Raw card",
            "skills": [{"id": "extra", "usage_notes": "Preserved for routing"}],
        }
        client = AgentRegistryClient(
            "http://registry:4000",
            agent_secret="agent-secret",
        )

        agent_name, payload = client.build_payload(
            _test_agent_card(),
            raw_agent_card=raw_agent_card,
        )

        assert agent_name == "test-agent"
        assert payload["agent_card_params"] is raw_agent_card
        assert payload["static_headers"] == {"Authorization": "Bearer agent-secret"}

    def test_get_raw_agent_card_returns_loaded_dict(self):
        agent = PrometheusAgent(agent_name="MyAgent")
        agent.agent_card_dict = {
            "name": "My Agent",
            "skills": [
                {
                    "id": "analyze_thermal",
                    "inputSchema": {"type": "object", "required": ["material_id"]},
                }
            ],
        }

        assert agent.get_raw_agent_card()["skills"][0]["inputSchema"]["required"] == ["material_id"]

    def test_llm_client_helper_inherits_agent_name_and_context_key(self):
        agent = PrometheusAgent(agent_name="Trace Agent")
        context = MagicMock(spec=RequestContext)
        part = MagicMock()
        part.root = DataPart(data={"provided_inputs": {"llm_api_key": "structured-key"}})
        context.message.parts = [part]

        client = agent.llm_client(context, config=LLMConfig(proxy_url="http://proxy"))

        assert isinstance(client, AsyncLLMClient)
        assert client.config.app_name == "Trace Agent"
        assert client.config.api_key == "structured-key"

    def test_default_lifespan_is_a_no_op(self):
        agent = PrometheusAgent(agent_name="MyAgent")

        async def run_lifespan():
            async with agent.lifespan(app=None):
                return "ok"

        assert asyncio.run(run_lifespan()) == "ok"

    def test_custom_lifespan_runs_startup_and_shutdown(self):
        events = []

        class TestAgent(PrometheusAgent):
            @asynccontextmanager
            async def lifespan(self, app):
                events.append(("startup", app))
                try:
                    yield
                finally:
                    events.append(("shutdown", app))

        agent = TestAgent(agent_name="MyAgent")
        sentinel_app = object()

        async def run_lifespan():
            async with agent.lifespan(sentinel_app):
                events.append(("running", sentinel_app))

        asyncio.run(run_lifespan())

        assert events == [
            ("startup", sentinel_app),
            ("running", sentinel_app),
            ("shutdown", sentinel_app),
        ]

    def test_application_lifespan_starts_background_registration(self):
        events = []

        class TestAgent(PrometheusAgent):
            @asynccontextmanager
            async def lifespan(self, app):
                events.append("startup")
                try:
                    yield
                finally:
                    events.append("shutdown")

            async def register_with_registry_async(self, agent_card, **kwargs):
                events.append(("register", agent_card.name))

        agent = TestAgent(agent_name="MyAgent")
        app = SimpleNamespace(state=SimpleNamespace())
        agent_card = _test_agent_card()

        async def run_lifespan():
            async with agent._application_lifespan(
                app,
                agent_card,
                register_on_startup=True,
            ):
                events.append("running")
                await asyncio.sleep(0)

        asyncio.run(run_lifespan())

        assert events == ["startup", "running", ("register", "Test Agent"), "shutdown"]
        assert app.state.registry_registration_task.done()

    def test_configure_auth_requires_secret_by_default(self, monkeypatch):
        agent = PrometheusAgent(agent_name="MyAgent")
        app = Starlette()
        monkeypatch.delenv("AGENT_SECRET", raising=False)
        monkeypatch.delenv("AGENT_SECRET_REQUIRED", raising=False)

        with pytest.raises(RuntimeError, match="AGENT_SECRET_REQUIRED=true"):
            agent._configure_auth(app)

    def test_configure_auth_can_be_disabled(self, monkeypatch):
        agent = PrometheusAgent(agent_name="MyAgent")
        app = Starlette()
        monkeypatch.delenv("AGENT_SECRET", raising=False)
        monkeypatch.setenv("AGENT_SECRET_REQUIRED", "false")

        agent._configure_auth(app)

        assert app.user_middleware == []

    def test_build_app_sets_components_and_routes_without_registration(self, monkeypatch):
        class TestAgent(PrometheusAgent):
            async def _execute(self, params, context, event_queue):
                return {"ok": True}

        agent = TestAgent(agent_name="MyAgent")
        agent_card = _test_agent_card()
        monkeypatch.setattr(agent, "load_agent_card", lambda: agent_card)
        monkeypatch.setenv("AGENT_SECRET_REQUIRED", "false")

        app = agent.build_app(register_on_startup=False)

        assert agent.agent_card is agent_card
        assert isinstance(agent.executor, PrometheusAgentExecutor)
        route_paths = {getattr(route, "path", None) for route in app.routes}
        assert "/health" in route_paths
        assert "/api/chat" in route_paths
        assert "/api/agent-card" in route_paths

    async def test_build_app_debug_chat_route_executes_agent(self, monkeypatch):
        class TestAgent(PrometheusAgent):
            async def _execute(self, params, context, event_queue):
                return {
                    "message": params.get("message"),
                    "context_id": context.context_id,
                }

        agent = TestAgent(agent_name="MyAgent")
        monkeypatch.setattr(agent, "load_agent_card", _test_agent_card)
        monkeypatch.setenv("AGENT_SECRET_REQUIRED", "false")
        app = agent.build_app(register_on_startup=False)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/chat",
                json={
                    "params": {"message": "hello"},
                    "conversation_id": "conv-1",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["context_id"] == "conv-1"
        assert payload["result"] == {"message": "hello", "context_id": "conv-1"}

    def test_agent__execute_not_implemented(self):
        """Test that base agent raises NotImplementedError for _execute."""
        agent = PrometheusAgent(agent_name="MyAgent")

        mock_context = MagicMock(spec=RequestContext)
        mock_queue = AsyncMock(spec=EventQueue)

        with pytest.raises(NotImplementedError):
            asyncio.run(agent._execute({}, mock_context, mock_queue))

    def test_send_input_required_emits_canonical_data_part(self):
        """Test INPUT_REQUIRED helper emits a final status with structured payload."""
        agent = PrometheusAgent(agent_name="MyAgent")
        context = MagicMock(spec=RequestContext)
        context.task_id = "task-1"
        context.context_id = "ctx-1"
        queue = AsyncMock(spec=EventQueue)

        asyncio.run(
            agent.send_input_required(
                context=context,
                event_queue=queue,
                missing_inputs=[
                    MissingInput(
                        name="temperature_c",
                        description="Operating temperature in Celsius.",
                        user_prompt="What operating temperature should I use?",
                        type="number",
                        resolvable_from_context=True,
                    )
                ],
                hint="Thermal analysis requires a temperature.",
            )
        )

        queue.enqueue_event.assert_called_once()
        event = queue.enqueue_event.call_args[0][0]
        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.input_required
        part = event.status.message.parts[0].root
        assert isinstance(part, DataPart)
        assert part.data["hint"] == "Thermal analysis requires a temperature."
        assert part.data["missing_inputs"][0]["name"] == "temperature_c"

    def test_create_executor_returns_delegating_executor(self):
        """Test that create_executor returns the standard delegating executor."""

        class TestAgent(PrometheusAgent):
            async def _execute(self, params, context, event_queue):
                return {"result": "test"}

        agent = TestAgent(agent_name="TestAgent")
        executor = agent.create_executor()

        assert isinstance(executor, DelegatingPrometheusAgentExecutor)
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

    def test_full_execution_flow(self):
        """Test complete execution flow with a concrete agent."""

        class EchoAgent(PrometheusAgent):
            async def _execute(self, params, context, event_queue):
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
        asyncio.run(executor.execute(context, queue))

        # Verify the flow
        calls = queue.enqueue_event.call_args_list

        # Working status
        assert calls[0][0][0].status.state == TaskState.working

        # Completed status with canonical final payload
        assert calls[1][0][0].status.state == TaskState.completed
        text_content = calls[1][0][0].status.message.parts[0].root.text
        result = json.loads(text_content)
        assert result["echo"] == "Hello, World!"
        assert result["task_id"] == "echo-task-1"


class TestPrometheusWorker:
    """Tests for PrometheusWorker + PrometheusAgent.run_worker."""

    def _agent(self):
        return PrometheusAgent(agent_name="Worker Agent")

    def _context(self):
        ctx = MagicMock(spec=RequestContext)
        ctx.task_id = "task-1"
        ctx.context_id = "conv-1"
        return ctx

    class _RecordingQueue:
        def __init__(self):
            self.events = []

        async def enqueue_event(self, event):
            self.events.append(event)

    def test_run_worker_forwards_events_and_returns_result(self):
        """Events a worker emits (status updates and JSON artifacts) are forwarded
        to the A2A event queue in order, and run_worker returns the worker's
        run() result. Status updates are non-final; the artifact carries its
        payload as a data part."""
        queue_ = self._RecordingQueue()

        class DemoWorker(PrometheusWorker):
            def run(self):
                self.emit_status_update("step 1")
                self.emit_json_artifact({"k": 1}, name="partial", json_type="demo.v1")
                self.emit_status_update("step 2")
                return {"status": "success", "n": 2}

        agent = self._agent()
        worker = DemoWorker()
        result = asyncio.run(
            agent.run_worker(worker, self._context(), queue_, poll_interval=0.01)
        )

        assert result == {"status": "success", "n": 2}
        kinds = [type(e).__name__ for e in queue_.events]
        assert kinds == [
            "TaskStatusUpdateEvent",
            "TaskArtifactUpdateEvent",
            "TaskStatusUpdateEvent",
        ]
        # Status text is preserved and non-final (the base executor finalizes).
        assert queue_.events[0].status.message.parts[0].root.text == "step 1"
        assert queue_.events[0].final is False
        # The JSON artifact carries the payload as a data part.
        artifact = queue_.events[1].artifact
        assert artifact.name == "partial"
        assert artifact.parts[0].root.data == {"k": 1}

    def test_run_worker_propagates_worker_exception(self):
        """An exception raised in worker.run() propagates out of run_worker (so the
        base executor still emits a failed status) rather than being swallowed."""
        queue_ = self._RecordingQueue()

        class BoomWorker(PrometheusWorker):
            def run(self):
                raise RuntimeError("boom")

        agent = self._agent()
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(
                agent.run_worker(BoomWorker(), self._context(), queue_, poll_interval=0.01)
            )

    def test_run_worker_cancellation_signals_worker_cooperatively(self):
        """Cancelling the run_worker task sets the worker's cancel flag so a
        cooperative worker (one that checks self.cancelled) stops, instead of
        being abandoned -- threads cannot be force-killed."""
        import time as _time

        queue_ = self._RecordingQueue()

        class LoopWorker(PrometheusWorker):
            def run(self):
                while not self.cancelled:
                    _time.sleep(0.01)
                return {"status": "cancelled"}

        agent = self._agent()
        worker = LoopWorker()

        async def go():
            task = asyncio.create_task(
                agent.run_worker(worker, self._context(), queue_, poll_interval=0.01)
            )
            await asyncio.sleep(0.05)  # let the worker start
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(go())
        assert worker.cancelled is True

    def test_emit_before_bind_raises(self):
        """Emitting from a worker that hasn't been bound to a request (i.e. not
        run via run_worker) raises a clear error instead of failing obscurely."""
        worker = PrometheusWorker()
        with pytest.raises(RuntimeError, match="not bound"):
            worker.emit_status_update("nope")


class TestDeclareLongRunning:
    """Tests for PrometheusAgent.declare_long_running (proactive detach signal)."""

    def _context(self):
        ctx = MagicMock(spec=RequestContext)
        ctx.task_id = "task-1"
        ctx.context_id = "conv-1"
        return ctx

    class _RecordingQueue:
        def __init__(self):
            self.events = []

        async def enqueue_event(self, event):
            self.events.append(event)

    def test_emits_nonfinal_working_with_background_metadata(self):
        agent = PrometheusAgent(agent_name="Long Agent")
        queue_ = self._RecordingQueue()
        asyncio.run(
            agent.declare_long_running(self._context(), queue_, estimate_seconds=120)
        )
        assert len(queue_.events) == 1
        event = queue_.events[0]
        assert event.status.state == TaskState.working
        assert event.final is False
        assert event.metadata["background"] is True
        assert event.metadata["estimate_seconds"] == 120.0
        # A default message naming the estimate is emitted.
        assert "120" in event.status.message.parts[0].root.text

    def test_custom_message_and_extra_metadata_merge(self):
        agent = PrometheusAgent(agent_name="Long Agent")
        queue_ = self._RecordingQueue()
        asyncio.run(
            agent.declare_long_running(
                self._context(),
                queue_,
                message="custom",
                metadata={"job_kind": "sim"},
            )
        )
        event = queue_.events[0]
        assert event.metadata["background"] is True
        assert event.metadata["job_kind"] == "sim"
        assert "estimate_seconds" not in event.metadata
        assert event.status.message.parts[0].root.text == "custom"
