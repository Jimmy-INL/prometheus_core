"""
PrometheusAgent - Base class for A2A agents with built-in authentication and registry support.

This module provides a base class that handles all the boilerplate for creating
A2A-enabled agents, allowing you to focus on your agent's core logic.
"""

import os
import json
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Mapping, Optional
from typing import Sequence, cast
from datetime import datetime
from pathlib import Path
from starlette.responses import JSONResponse

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from .task_store import RedisTaskStore
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Artifact,
    DataPart,
    FilePart,
    FileWithUri,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from .middleware import BearerTokenMiddleware
from .artifact_resolver import ArtifactResolver
from .artifacts import ArtifactReference, ArtifactRegistry
from .context_state import ContextStateStore
from .debug_routes import add_debug_chat_route
from .events import (
    build_artifact_metadata as _build_artifact_metadata,
    build_data_artifact_event,
    context_id as event_context_id,
    context_task_id,
    emit_status_update,
    normalize_producer_agent_id as _normalize_producer_agent_id,
)
from .worker import PrometheusWorker
from .registry import AgentRegistryClient
from ..storage_client.async_client import AsyncStorageClient
from ..storage_client.connection import ConnectionConfig
from ..storage_client.models.item import ItemUpdate
import uvicorn

logger = logging.getLogger(__name__)


class _TrackedEventQueue:
    """Event queue wrapper that tracks finalization-related events."""

    def __init__(self, event_queue: EventQueue):
        self._event_queue = event_queue
        self.seen_final_status = False

    async def enqueue_event(self, event: Any) -> None:
        """Forward event to wrapped queue while tracking task-finalization signals."""
        if isinstance(event, TaskStatusUpdateEvent) and event.final:
            self.seen_final_status = True

        await self._event_queue.enqueue_event(event)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._event_queue, name)


@dataclass
class MissingInput:
    """Canonical missing-input descriptor for INPUT_REQUIRED responses."""

    name: str
    description: str
    user_prompt: str
    type: str
    options: Optional[List[str]] = None
    resolvable_from_context: bool = False
    sensitive: bool = False
    required: bool = True


def build_input_required_payload(
    missing_inputs: List[MissingInput],
    hint: str,
) -> Dict[str, Any]:
    """Serialize missing-input requirements into the canonical payload shape."""
    return {
        "missing_inputs": [asdict(item) for item in missing_inputs],
        "hint": str(hint or "").strip(),
    }


class PrometheusAgentExecutor(AgentExecutor):
    """
    Base executor for Prometheus agents.

    Handles parameter extraction, status updates, and error handling.
    Subclasses only need to implement _execute().
    """

    def __init__(self, agent_name: str = "Agent"):
        """
        Initialize the agent executor.

        Args:
            agent_name: Name of the agent (for logging)
        """
        super().__init__()
        self.agent_name = agent_name
        logger.info(f"Initialized {agent_name}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the agent task.

        This method handles the standard A2A execution flow:
        1. Extract parameters from message
        2. Send "working" status
        3. Call _execute() (implemented by subclass)
        4. Send completion status with the canonical final structured response
        5. Handle errors

        Args:
            context: A2A request context containing the message and parameters
            event_queue: Queue for sending status updates
        """
        tracked_queue: Optional[_TrackedEventQueue] = None
        try:
            logger.info(f"Starting {self.agent_name} execution")

            # Extract parameters from the message
            params = self._extract_params(context)
            tracked_queue = _TrackedEventQueue(event_queue)

            # Send "working" status
            await emit_status_update(
                context=context,
                event_queue=tracked_queue,
                state=TaskState.working,
                final=False,
            )

            # Perform the main analysis (implemented by subclass), with a
            # background keepalive so streaming connections do not time out
            # during long gaps between substantive status updates.
            result = await self._execute_with_heartbeat(params, context, tracked_queue)

            # Agent can fully control finalization for advanced/streaming use cases.
            # If it already emitted a final status, skip automatic completion events.
            if not tracked_queue.seen_final_status:
                await emit_status_update(
                    context=context,
                    event_queue=tracked_queue,
                    state=TaskState.completed,
                    final=True,
                    message=json.dumps(result, default=str),
                )
            else:
                logger.debug(
                    "%s emitted final status in _execute(); skipping automatic finalization",
                    self.agent_name,
                )

            logger.info(f"{self.agent_name} execution completed successfully")

        except Exception as e:
            logger.error(f"Error during execution: {str(e)}", exc_info=True)
            # Avoid sending contradictory terminal states if the agent already finalized.
            if not tracked_queue or not tracked_queue.seen_final_status:
                await emit_status_update(
                    context=context,
                    event_queue=tracked_queue or event_queue,
                    state=TaskState.failed,
                    final=True,
                )
            raise

    @staticmethod
    def _heartbeat_interval() -> float:
        """Seconds between automatic keepalive events.

        Configured via ``PROMETHEUS_HEARTBEAT_INTERVAL`` (seconds, default 15),
        comfortably below typical proxy/idle-connection timeouts. Must be a
        positive number: a non-numeric or non-positive value raises
        ``ValueError`` rather than silently defaulting. Heartbeats cannot be
        disabled -- a long ``_execute`` must not run without keepalives.
        """
        raw = (os.getenv("PROMETHEUS_HEARTBEAT_INTERVAL") or "15").strip()
        value = float(raw)
        if value <= 0:
            raise ValueError("PROMETHEUS_HEARTBEAT_INTERVAL must be a positive number of seconds")
        return value

    async def _execute_with_heartbeat(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        tracked_queue: "_TrackedEventQueue",
    ) -> Dict[str, Any]:
        """Run ``_execute`` while emitting periodic keepalive status events."""
        interval = self._heartbeat_interval()
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(context, tracked_queue, interval, stop_event)
        )
        try:
            return await self._execute(params, context, cast(EventQueue, tracked_queue))
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _heartbeat_loop(
        self,
        context: RequestContext,
        tracked_queue: "_TrackedEventQueue",
        interval: float,
        stop_event: asyncio.Event,
    ) -> None:
        """Emit non-final, message-less ``working`` events at a fixed interval.

        These keep the streaming HTTP connection alive (and reset idle timers in
        intermediary proxies) without surfacing UI text: consumers ignore status
        updates that carry no message and are tagged ``metadata.heartbeat``.
        """
        try:
            while True:
                try:
                    # Sleep for the interval, waking early if work has finished.
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                    return
                except asyncio.TimeoutError:
                    pass

                # Never emit after the task has been finalized.
                if tracked_queue.seen_final_status:
                    return

                try:
                    await emit_status_update(
                        context=context,
                        event_queue=tracked_queue,
                        state=TaskState.working,
                        final=False,
                        metadata={"heartbeat": True},
                    )
                except Exception as exc:  # a keepalive must never break execution
                    # A transient emit failure shouldn't permanently stop the
                    # keepalive; log and retry on the next interval.
                    logger.debug("Heartbeat emit failed for %s: %s", self.agent_name, exc)
                    continue
        except asyncio.CancelledError:
            raise

    def _extract_params(self, context: RequestContext) -> Dict[str, Any]:
        """
        Extract parameters from the A2A message context.

        Args:
            context: A2A request context

        Returns:
            Dict of extracted parameters. Always includes ``skill_id`` when
            the caller placed a ``skillId`` key in the message metadata.

        Raises:
            ValueError: If message format is invalid
        """
        # Get user input text from the context
        text = context.get_user_input()

        if not text:
            params: Dict[str, Any] = {}
        else:
            try:
                params = json.loads(text)
            except json.JSONDecodeError:
                # If not valid JSON, treat the text as a plain message
                logger.debug("Message is not JSON; treating it as plain text")
                params = {"message": text}
            else:
                if not isinstance(params, dict):
                    params = {"value": params}

        # Inject skill_id from message metadata so agents can dispatch on
        # which skill was invoked without needing an explicit 'action' param.
        message = getattr(context, "message", None)
        if message and isinstance(message.metadata, dict):
            skill_id = message.metadata.get("skillId")
            if skill_id and "skill_id" not in params:
                params["skill_id"] = str(skill_id)

        logger.info("Extracted parameter keys: %s", sorted(params.keys()))
        return params

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Process the analysis request.

        OVERRIDE THIS METHOD in your agent subclass to implement your agent's logic.

        Args:
            params: Parameters extracted from the A2A message
            context: A2A request context
            event_queue: Queue for sending progress updates

        Returns:
            Dict containing the analysis results

        Example:
            ```python
            async def _execute(self, params, context, event_queue):
                input_data = params.get("input_data")

                await emit_status_update(
                    context=context,
                    event_queue=event_queue,
                    state=TaskState.working,
                    final=False,
                    message="Running analysis.",
                )

                # Do your work
                result = do_something(input_data)

                return {
                    "status": "success",
                    "result": result
                }
            ```
        """
        raise NotImplementedError(
            "Subclasses must implement _execute() method. "
            "This is where your agent's core logic should go."
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Handle task cancellation.

        Args:
            context: A2A request context
            event_queue: Queue for sending status updates
        """
        logger.info(f"Cancellation requested for {self.agent_name}")
        await emit_status_update(
            context=context,
            event_queue=event_queue,
            state=TaskState.canceled,
            final=True,
        )


class DelegatingPrometheusAgentExecutor(PrometheusAgentExecutor):
    """Executor that delegates agent work to a provided async callback."""

    def __init__(
        self,
        *,
        agent_name: str,
        execute_fn: Callable[
            [Dict[str, Any], RequestContext, EventQueue],
            Awaitable[Dict[str, Any]],
        ],
    ):
        super().__init__(agent_name=agent_name)
        self._execute_fn = execute_fn

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """Delegate to the owning agent's `_execute` implementation."""
        return await self._execute_fn(params, context, event_queue)


class PrometheusAgent:
    """
    Base class for Prometheus A2A agents.

    This class handles all the boilerplate:
    - Loading agent card from JSON
    - Setting up Bearer token authentication
    - Registering with the registry
    - Starting the HTTP server with A2A protocol

    To create an agent:
    1. Inherit from PrometheusAgent
    2. Override _execute() method
    3. Call run()

    Example:
        ```python
        from prometheus_api.agent import PrometheusAgent

        class MyAgent(PrometheusAgent):
            async def _execute(self, params, context, event_queue):
                # Your logic here
                return {"status": "success"}

        if __name__ == "__main__":
            agent = MyAgent(agent_name="My Agent")
            agent.run()
        ```
    """

    @staticmethod
    def registry_url() -> str:
        """Return the configured LiteLLM registry URL with the agent default applied."""
        return os.getenv("REGISTRY_URL", "http://litellm:4000").strip()

    def __init__(self, agent_name: str = "Agent", agent_card_path: Optional[str] = None):
        """
        Initialize the Prometheus agent.

        Args:
            agent_name: Name of the agent (for logging and metadata)
            agent_card_path: Path to agent_card.json (defaults to ./agent_card.json)
        """
        self.agent_name = agent_name
        self.agent_card_path = agent_card_path or "agent_card.json"

        # Will be set during initialization
        self.agent_card: Optional[AgentCard] = None
        self.agent_card_dict: Optional[Dict[str, Any]] = None  # Raw dict for registry registration
        self.executor: Optional[PrometheusAgentExecutor] = None
        self.artifact_registry = ArtifactRegistry()
        self.artifact_resolver = ArtifactResolver(self.artifact_registry)
        self.context_state_store = ContextStateStore()

    def get_raw_agent_card(self) -> Dict[str, Any]:
        """Return the canonical raw agent-card payload used for planning metadata."""
        if self.agent_card_dict is None:
            raise RuntimeError("Agent card has not been loaded yet")
        return self.agent_card_dict

    def load_context_state(self, context_id: str) -> Dict[str, Any]:
        """Load persisted agent-local state for one A2A contextId."""
        return self.context_state_store.load(self._producer_agent_id, str(context_id or ""))

    def save_context_state(self, context_id: str, state: Dict[str, Any]) -> None:
        """Persist agent-local state for one A2A contextId."""
        self.context_state_store.save(self._producer_agent_id, str(context_id or ""), state)

    def get_provided_inputs(self, context: RequestContext) -> Dict[str, Any]:
        """Extract structured follow-up inputs from incoming DataParts."""
        message = getattr(context, "message", None)
        if message is None:
            return {}

        provided: Dict[str, Any] = {}
        for part in getattr(message, "parts", []) or []:
            root = getattr(part, "root", None)
            if not isinstance(root, DataPart):
                continue
            data = dict(root.data or {})
            if isinstance(data.get("provided_inputs"), dict):
                provided.update(data["provided_inputs"])
            else:
                provided.update(data)
        return provided

    def llm_client(self, context: RequestContext, **kwargs: Any) -> Any:
        """Create an AsyncLLMClient that inherits this agent's name for tracing."""
        from ..llm_client import AsyncLLMClient

        return AsyncLLMClient.from_a2a_context(
            context,
            app_name=self.agent_name,
            **kwargs,
        )

    @staticmethod
    def pending_hint(
        pending_subagent_requests: Optional[Any],
        default: str = "I need some additional information to proceed:",
    ) -> str:
        """Extract the user-facing hint from a pending INPUT_REQUIRED request.

        Accepts either a single pending-request dict or a list of them.
        Returns the hint from the first entry that has one, or the default.
        """
        if not pending_subagent_requests:
            return default
        entries = (
            pending_subagent_requests
            if isinstance(pending_subagent_requests, list)
            else [pending_subagent_requests]
        )
        for entry in entries:
            hint = (entry or {}).get("hint")
            if hint:
                return str(hint)
        return default

    async def send_input_required(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        missing_inputs: List[MissingInput],
        hint: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a canonical final INPUT_REQUIRED status message."""
        payload = build_input_required_payload(missing_inputs, hint=hint)
        task_id = context_task_id(context)
        context_id = event_context_id(context)
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                final=True,
                status=TaskStatus(
                    state=TaskState.input_required,
                    message=Message(
                        message_id=str(uuid.uuid4()),
                        role=Role.agent,
                        parts=[
                            Part(
                                root=DataPart(
                                    data=payload, metadata={"mime_type": "application/json"}
                                )
                            )
                        ],
                        context_id=context_id,
                        task_id=task_id,
                    ),
                ),
                metadata=metadata,
            )
        )

    @staticmethod
    def _context_conversation_id(context: RequestContext) -> str:
        """Return the effective conversation scope key for registry operations."""
        return event_context_id(context)

    @property
    def _producer_agent_id(self) -> str:
        """Stable producer identifier for emitted artifacts and registry entries."""
        return _normalize_producer_agent_id(self.agent_name)

    def register_artifact_reference(
        self,
        context: RequestContext,
        reference: ArtifactReference,
    ) -> ArtifactReference:
        """Persist an artifact reference under the current conversation scope.

        Used by producer helpers and auto-registration in `send_json_artifact`.
        """
        if not reference.conversation_id:
            reference.conversation_id = self._context_conversation_id(context)
        if not reference.producer_agent_id:
            reference.producer_agent_id = self._producer_agent_id
        return self.artifact_registry.register(reference)

    async def _emit_text_artifact(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        text: str,
        name: str,
        artifact_id: str,
        append: bool = False,
        last_chunk: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a text artifact from public helper methods."""
        task_id = context_task_id(context)
        context_id = event_context_id(context)
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=artifact_id,
                    name=name,
                    metadata=_build_artifact_metadata(
                        context=context,
                        agent_name=self.agent_name,
                    ),
                    parts=[Part(root=TextPart(text=text, metadata={"mime_type": "text/plain"}))],
                ),
                append=append,
                last_chunk=last_chunk,
                metadata=metadata,
            )
        )

    async def _emit_file_artifact(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        uri: str,
        name: str,
        mime_type: Optional[str],
        artifact_id: str,
        description: Optional[str] = None,
        append: bool = False,
        last_chunk: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a URI-backed file artifact from public helper methods."""
        task_id = context_task_id(context)
        context_id = event_context_id(context)
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=artifact_id,
                    name=name,
                    description=description,
                    metadata=_build_artifact_metadata(
                        context=context,
                        agent_name=self.agent_name,
                    ),
                    parts=[
                        Part(
                            root=FilePart(
                                file=FileWithUri(
                                    uri=uri,
                                    mime_type=mime_type,
                                    name=name,
                                ),
                                metadata=metadata,
                            )
                        )
                    ],
                ),
                append=append,
                last_chunk=last_chunk,
                metadata=metadata,
            )
        )

    def list_artifact_references(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> List[ArtifactReference]:
        """List known references for one conversation (newest-first)."""
        return self.artifact_registry.list(conversation_id, limit=limit)

    def resolve_artifact_reference(
        self,
        conversation_id: str,
        artifact_id: str,
    ) -> Optional[ArtifactReference]:
        """Resolve one artifact reference by canonical ID."""
        return self.artifact_registry.resolve_by_id(conversation_id, artifact_id)

    def resolve_artifact_by_name(
        self,
        conversation_id: str,
        name_or_alias: str,
    ) -> Optional[ArtifactReference]:
        """Resolve one artifact reference by user-facing name/alias."""
        return self.artifact_registry.resolve_by_name(conversation_id, name_or_alias)

    async def get_artifact_file_path(
        self,
        artifact_id: str,
        *,
        context: Optional[RequestContext] = None,
        conversation_id: Optional[str] = None,
        artifacts: Optional[Sequence[Mapping[str, Any]]] = None,
        cache_dir: Optional[Path] = None,
        allowed_file_roots: Optional[Sequence[Path | str]] = None,
        force_download: bool = False,
    ) -> Path:
        """Resolve an artifact ID to a reachable local file path.

        Delegates to :class:`ArtifactResolver`; see its docs for cache layout,
        local-file validation, and inline materialization semantics.
        """
        resolved_conversation_id = str(
            conversation_id
            or (self._context_conversation_id(context) if context is not None else "")
        ).strip()
        if not resolved_conversation_id:
            raise ValueError("conversation_id or context is required")

        return await self.artifact_resolver.get_artifact_file_path(
            artifact_id,
            conversation_id=resolved_conversation_id,
            artifacts=artifacts,
            cache_dir=cache_dir,
            allowed_file_roots=allowed_file_roots,
            force_download=force_download,
        )

    def load_agent_card(self) -> AgentCard:
        """
        Load the agent card from JSON file and update URL from environment.

        Returns:
            AgentCard object with runtime URL

        Raises:
            FileNotFoundError: If agent_card.json doesn't exist
            json.JSONDecodeError: If agent_card.json is invalid
        """
        agent_card_path = Path(self.agent_card_path)

        # If relative path, look in the directory of the calling script
        if not agent_card_path.is_absolute():
            # Get the directory of the main script
            import __main__

            if hasattr(__main__, "__file__"):
                script_dir = Path(__main__.__file__).parent
                agent_card_path = script_dir / agent_card_path

        try:
            with open(agent_card_path, "r") as f:
                agent_card_dict = json.load(f)
        except FileNotFoundError:
            logger.error(f"agent_card.json not found at {agent_card_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in agent_card.json: {e}")
            raise

        # EXTERNAL_AGENT_URL, if set, is the full URL the registry uses to reach
        # this agent (use when the agent is port-mapped or on a different host).
        # Otherwise derive from the container hostname (Docker sets this to the
        # service name automatically) and AGENT_PORT.
        import socket

        port = os.getenv("AGENT_PORT", "8000")
        agent_card_dict["url"] = (
            os.getenv("EXTERNAL_AGENT_URL") or f"http://{socket.gethostname()}:{port}"
        )

        # Store the raw dict for registry registration
        self.agent_card_dict = agent_card_dict

        # Convert capabilities dict to AgentCapabilities object
        capabilities_dict = agent_card_dict.get("capabilities", {})
        capabilities = AgentCapabilities(
            streaming=capabilities_dict.get("streaming", False),
            push_notifications=capabilities_dict.get("pushNotifications", False),
        )

        # Convert skills list to AgentSkill objects
        skills = [
            AgentSkill(
                id=skill["id"],
                name=skill["name"],
                description=skill.get("description", ""),
                tags=skill.get("tags", []),
            )
            for skill in agent_card_dict.get("skills", [])
        ]

        # Create the AgentCard object
        agent_card = AgentCard(
            name=agent_card_dict["name"],
            description=agent_card_dict["description"],
            url=agent_card_dict["url"],
            version=agent_card_dict.get("version", "1.0.0"),
            capabilities=capabilities,
            skills=skills,
            default_input_modes=agent_card_dict.get("defaultInputModes", ["text"]),
            default_output_modes=agent_card_dict.get("defaultOutputModes", ["text"]),
        )

        logger.info(f"Loaded agent card: {agent_card.name} v{agent_card.version}")
        logger.info(f"Agent URL: {agent_card.url}")

        return agent_card

    def _registry_client(self) -> Optional[AgentRegistryClient]:
        """Return a LiteLLM registry client, or None when registration is disabled."""
        registry_url = self.registry_url()
        if not registry_url:
            logger.info("REGISTRY_URL not set - skipping agent registration")
            return None
        return AgentRegistryClient.from_env(registry_url)

    def register_with_registry(
        self,
        agent_card: AgentCard,
        *,
        max_retries: Optional[int] = None,
        initial_delay: float = 2.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
    ) -> None:
        """
        Register this agent with LiteLLM's A2A gateway.

        Retries with exponential backoff until success or max_retries is
        exhausted. max_retries defaults to REGISTRY_MAX_RETRIES env var (default 10).
        On final failure the agent starts unregistered with a warning logged.
        """
        registry_client = self._registry_client()
        if registry_client is None:
            return
        registry_client.register_with_retries(
            agent_card,
            raw_agent_card=self.agent_card_dict,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
        )

    async def register_with_registry_async(
        self,
        agent_card: AgentCard,
        *,
        max_retries: Optional[int] = None,
        initial_delay: float = 2.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
    ) -> None:
        """
        Register this agent with LiteLLM's A2A gateway without blocking the event loop.

        This is the registration path used by `build_app()`/`run()` during Starlette lifespan
        startup. It keeps the same retry policy as `register_with_registry()`.
        """
        registry_client = self._registry_client()
        if registry_client is None:
            return
        await registry_client.register_with_retries_async(
            agent_card,
            raw_agent_card=self.agent_card_dict,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
        )

    def create_executor(self) -> PrometheusAgentExecutor:
        """
        Create the agent executor.

        Override this method only when you need to replace the standard
        Prometheus execution lifecycle. Normal agents should override
        `PrometheusAgent._execute()` instead.

        Returns:
            Agent executor instance
        """
        return DelegatingPrometheusAgentExecutor(
            agent_name=self.agent_name,
            execute_fn=self._execute,
        )

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Process the analysis request.

        OVERRIDE THIS METHOD to implement your agent's logic.

        Args:
            params: Parameters extracted from the A2A message
            context: A2A request context
            event_queue: Queue for sending progress updates

        Returns:
            Dict containing the analysis results

        Example:
            ```python
            async def _execute(self, params, context, event_queue):
                input_data = params.get("input_data")

                await self.send_status_update(
                    context,
                    event_queue,
                    message="Running analysis.",
                )

                # Your logic here
                result = do_work(input_data)

                return {"status": "success", "result": result}
            ```
        """
        raise NotImplementedError(
            "You must override _execute() in your agent subclass. "
            "This is where your agent's core logic should be implemented."
        )

    async def send_status_update(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        state: TaskState = TaskState.working,
        final: bool = False,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Send a task status event.

        This helper is optional and does not change `_execute` signature.
        """
        await emit_status_update(
            context=context,
            event_queue=event_queue,
            state=state,
            final=final,
            message=message,
            metadata=metadata,
        )

    async def declare_long_running(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        estimate_seconds: Optional[float] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Declare up front that this skill will run for a long time.

        Emits a non-final ``working`` status tagged ``metadata.background = True``
        so the orchestrator can *proactively* detach the turn — handing control
        back to the user immediately instead of waiting out its soft deadline —
        and deliver the result out-of-band when the work finishes. Call this near
        the start of ``_execute`` for simulation-class skills that you know will
        outlive a normal request.

        The task itself keeps running exactly as before; this only flags it as a
        background candidate. ``estimate_seconds`` (if given) is forwarded in the
        event metadata as a hint for UI/scheduling.
        """
        payload: Dict[str, Any] = {"background": True}
        if estimate_seconds is not None:
            payload["estimate_seconds"] = float(estimate_seconds)
        if metadata:
            payload.update(metadata)
        if message is None:
            if estimate_seconds is not None:
                message = f"Running in the background (estimated ~{int(estimate_seconds)}s)."
            else:
                message = "Running in the background."
        await emit_status_update(
            context=context,
            event_queue=event_queue,
            state=TaskState.working,
            final=False,
            message=message,
            metadata=payload,
        )

    async def run_worker(
        self,
        worker: PrometheusWorker,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """Run a :class:`PrometheusWorker` on a worker thread, forwarding the
        events it emits to the A2A event queue from the event loop.

        Use this to run genuinely blocking work (a synchronous SDK, a legacy
        library, a CPU loop) without freezing the loop: the blocking ``run()``
        executes off-loop while this coroutine drains the worker's mailbox and
        enqueues each event, ``await``-ing a short sleep between polls so the
        keepalive heartbeat and streaming keep flowing.

        Returns the worker's ``run()`` result and re-raises any exception it
        raised (so the base executor still emits a ``failed`` status). On
        cancellation (e.g. the caller disconnects) the worker is asked to stop
        cooperatively via ``worker.cancel()`` — threads cannot be force-killed,
        so the worker must check ``self.cancelled``.
        """
        worker._bind(context, self.agent_name)
        task = asyncio.create_task(asyncio.to_thread(worker.run))
        try:
            while not task.done():
                await self._forward_worker_events(worker, event_queue)
                await asyncio.sleep(poll_interval)
            # Flush events emitted between the last poll and completion.
            await self._forward_worker_events(worker, event_queue)
            return await task
        except asyncio.CancelledError:
            worker.cancel()
            # Let the worker observe the flag and exit so we don't leak the
            # thread, then flush whatever it emitted on the way out.
            with suppress(Exception):
                await task
            await self._forward_worker_events(worker, event_queue)
            raise

    async def _forward_worker_events(
        self,
        worker: PrometheusWorker,
        event_queue: EventQueue,
    ) -> None:
        """Drain a worker's mailbox and enqueue each event on the loop."""
        for event in worker.drain():
            await event_queue.enqueue_event(event)

    async def send_json_artifact(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        payload: Any,
        name: str = "result",
        description: Optional[str] = None,
        json_type: Optional[str] = None,
        catalog_artifact: bool = False,
        artifact_id: Optional[str] = None,
        append: bool = False,
        last_chunk: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a JSON artifact event.

        Behavior:
        - Emits a native A2A data artifact.
        - Optionally registers inline JSON artifacts in the conversation catalog
          when `catalog_artifact=True`.

        Returns:
            The artifact_id used for this event (useful for chunked appends).
        """
        artifact_id = artifact_id or str(uuid.uuid4())

        if catalog_artifact:
            registered = self.register_artifact_reference(
                context,
                ArtifactReference(
                    artifact_id=artifact_id,
                    conversation_id=self._context_conversation_id(context),
                    name=name,
                    description=description or "",
                    mime_type="application/json",
                    json_type=json_type,
                    json_body=payload,
                    producer_agent_id=self._producer_agent_id,
                    metadata=dict(metadata or {}),
                ),
            )
            artifact_id = registered.artifact_id

        event, artifact_id = build_data_artifact_event(
            context=context,
            agent_name=self.agent_name,
            payload=payload,
            name=name,
            description=description,
            json_type=json_type,
            artifact_id=artifact_id,
            append=append,
            last_chunk=last_chunk,
            metadata=metadata,
        )
        await event_queue.enqueue_event(event)
        return artifact_id

    async def send_artifact_reference(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        name: str,
        description: str,
        uri: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        artifact_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactReference:
        """Register and emit a URI-backed artifact using a native A2A file part."""
        reference = ArtifactReference(
            artifact_id=artifact_id or str(uuid.uuid4()),
            conversation_id=self._context_conversation_id(context),
            name=name,
            description=description,
            uri=uri,
            mime_type=mime_type,
            size_bytes=size_bytes,
            producer_agent_id=self._producer_agent_id,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        registered = self.register_artifact_reference(context, reference)
        await self._emit_file_artifact(
            context=context,
            event_queue=event_queue,
            name=name,
            uri=uri,
            mime_type=mime_type,
            artifact_id=registered.artifact_id,
            description=description,
            metadata=metadata,
        )
        return registered

    async def send_deeplynx_artifact(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        *,
        file_path: Path,
        name: str,
        description: str,
        storage_config: ConnectionConfig,
        mime_type: Optional[str] = None,
        json_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactReference:
        """Upload a local file to DeepLynx and emit a deeplynx:// artifact reference.

        Uploads the file, then creates a DeepLynx item whose ``properties`` carry
        the artifact metadata (``mime_type``, ``json_type``, ``file_id``, and any
        extra ``metadata`` keys).  The resulting URI encodes the item so downstream
        consumers can retrieve both metadata and the raw file via the storage client.

        URI format::

            deeplynx://organizations/{org_id}/projects/{proj_id}/items/{item_id}

        Args:
            file_path: Local path of the file to upload.
            name: Human-readable artifact name.
            description: Human-readable artifact description.
            storage_config: DeepLynx ``ConnectionConfig`` (org, project, credentials).
            mime_type: MIME type of the file.  Defaults to ``application/octet-stream``.
            json_type: Optional semantic type identifier stored in item properties
                (e.g. ``"prometheus.my_agent.result.v1"``).
            artifact_id: Explicit artifact ID; auto-generated when omitted.
            tags: Tag names applied to the DeepLynx item and the local artifact catalog.
            metadata: Extra key/value pairs merged into the item ``properties`` and
                the ``ArtifactReference.metadata``.

        Returns:
            The registered ``ArtifactReference`` with ``uri`` set to the
            ``deeplynx://`` address and ``metadata`` containing
            ``deeplynx_item_id`` and ``deeplynx_file_id`` for quick resolution.
        """
        resolved_mime = mime_type or "application/octet-stream"

        async with AsyncStorageClient(storage_config) as client:
            file_meta = await client.files.upload(
                file_path,
                name=name,
                description=description,
            )

            # File upload creates a record in DeepLynx; update its properties to
            # carry artifact metadata rather than creating a separate item record.
            existing = await client.items.get(file_meta.id)
            merged_properties: Dict[str, Any] = dict(existing.properties or {})
            merged_properties.update(
                {
                    "mime_type": resolved_mime,
                    "file_id": file_meta.id,
                }
            )
            if json_type:
                merged_properties["json_type"] = json_type
            if file_meta.uri:
                merged_properties["file_uri"] = file_meta.uri
            if metadata:
                merged_properties.update(metadata)

            await client.items.update(
                file_meta.id,
                ItemUpdate(
                    name=name,
                    description=description,
                    properties=merged_properties,
                    class_id=existing.class_id,
                    original_id=existing.original_id,
                ),
            )
            if tags:
                await client.items.add_tags(file_meta.id, list(tags))

        uri = (
            f"deeplynx://organizations/{storage_config.organization_id}"
            f"/projects/{storage_config.project_id}"
            f"/items/{file_meta.id}"
        )
        return await self.send_artifact_reference(
            context=context,
            event_queue=event_queue,
            name=name,
            description=description,
            uri=uri,
            mime_type=resolved_mime,
            size_bytes=file_meta.size,
            artifact_id=artifact_id,
            tags=tags,
            metadata={
                **(metadata or {}),
                "deeplynx_item_id": file_meta.id,
                "deeplynx_file_id": file_meta.id,
            },
        )

    async def send_text_artifact(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        text: str,
        name: str = "result",
        artifact_id: Optional[str] = None,
        append: bool = False,
        last_chunk: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a text artifact event.

        Returns:
            The artifact_id used for this event (useful for chunked appends).
        """
        artifact_id = artifact_id or str(uuid.uuid4())
        await self._emit_text_artifact(
            context=context,
            event_queue=event_queue,
            text=text,
            name=name,
            artifact_id=artifact_id,
            append=append,
            last_chunk=last_chunk,
            metadata=metadata,
        )
        return artifact_id

    async def send_conversation_message(
        self,
        context: RequestContext,
        event_queue: EventQueue,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Emit a durable conversation-visible message payload.

        Use this for user-facing messages that should appear in chat history.
        This is distinct from transient status updates intended for progress UI.
        """
        payload = {"message": str(message)}
        meta = {"kind": "conversation_message", **dict(metadata or {})}
        return await self.send_json_artifact(
            context=context,
            event_queue=event_queue,
            payload=payload,
            name="conversation_message",
            metadata=meta,
        )

    def configure_app(self, app) -> None:
        """
        Optional hook to register additional routes or middleware on the Starlette app.

        Override in subclasses that need custom HTTP endpoints beyond A2A + /health + /api/chat.
        Override `lifespan()` for startup/shutdown behavior.
        """
        return

    @asynccontextmanager
    async def lifespan(self, app) -> AsyncIterator[None]:
        """
        Optional Starlette lifespan hook for startup/shutdown work.

        Override in subclasses that need app lifecycle management under
        Starlette 1.x-compatible lifespan semantics.
        """
        yield

    @staticmethod
    def _log_background_registration_result(task: asyncio.Task[None]) -> None:
        """Log unexpected background registration task failures."""
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Background registry registration task failed unexpectedly")

    @asynccontextmanager
    async def _application_lifespan(
        self,
        app,
        agent_card: AgentCard,
        *,
        register_on_startup: bool,
    ) -> AsyncIterator[None]:
        """Run subclass lifespan and start registry registration in the background."""
        registration_task: Optional[asyncio.Task[None]] = None
        async with self.lifespan(app):
            if register_on_startup:
                registration_task = asyncio.create_task(
                    self.register_with_registry_async(agent_card),
                    name=f"{self.agent_name}-registry-registration",
                )
                registration_task.add_done_callback(self._log_background_registration_result)
                with suppress(Exception):
                    app.state.registry_registration_task = registration_task

            try:
                yield
            finally:
                if registration_task and not registration_task.done():
                    registration_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await registration_task

    @staticmethod
    def _agent_secret_required() -> bool:
        return os.getenv("AGENT_SECRET_REQUIRED", "true").lower() in ["true", "1", "yes"]

    def _configure_auth(self, app) -> None:
        """Attach bearer-token authentication or fail fast for unsafe required config."""
        agent_secret = os.getenv("AGENT_SECRET")
        agent_secret_required = self._agent_secret_required()

        if not agent_secret_required:
            logger.warning("Bearer token authentication disabled (AGENT_SECRET_REQUIRED=false)")
            return

        if not agent_secret:
            raise RuntimeError("AGENT_SECRET_REQUIRED=true but AGENT_SECRET is not set")

        app.add_middleware(
            BearerTokenMiddleware,
            secret=agent_secret,
            required=True,
        )
        logger.info("Bearer token authentication enabled")

    def build_app(self, *, register_on_startup: bool = True):
        """
        Build the Starlette app for this agent.

        This method:
        1. Loads the agent card
        2. Creates the executor
        3. Sets up the HTTP server with A2A protocol
        4. Adds Bearer token authentication
        5. Starts registry registration during app lifespan

        Args:
            register_on_startup: Whether to start background LiteLLM registry registration
                when the app lifespan starts.
        """
        logger.info(f"Starting {self.agent_name}")

        # Load agent card
        agent_card = self.load_agent_card()
        self.agent_card = agent_card

        # Create executor
        executor = self.create_executor()
        self.executor = executor

        # Create request handler. Tasks are persisted in Redis by default so
        # background / long-running tasks survive an agent restart and can be
        # re-attached to. RedisTaskStore degrades to an in-process dict when
        # Redis is unavailable; set PROMETHEUS_TASK_STORE=memory to force the
        # SDK's volatile in-memory store. See docs/dev-docs/background-tasks.md.
        task_store_kind = os.getenv("PROMETHEUS_TASK_STORE", "redis").strip().lower()
        if task_store_kind == "memory":
            task_store: Any = InMemoryTaskStore()
            logger.info("Using in-memory task store (PROMETHEUS_TASK_STORE=memory)")
        else:
            task_store = RedisTaskStore()
            logger.info("Using Redis-backed task store")
        request_handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)

        # Create A2A application builder
        builder = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)

        @asynccontextmanager
        async def app_lifespan(app) -> AsyncIterator[None]:
            async with self._application_lifespan(
                app,
                agent_card,
                register_on_startup=register_on_startup,
            ):
                yield

        # Build the Starlette app
        app = builder.build(lifespan=app_lifespan)

        # add health endpoint
        app.add_route(
            "/health",
            lambda request: JSONResponse(
                {
                    "ok": True,
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
            methods=["GET"],
        )

        add_debug_chat_route(app, agent=self, executor=executor)

        async def api_agent_card(request):
            """Return the raw agent card with Prometheus-specific skill metadata."""
            return JSONResponse(self.get_raw_agent_card())

        app.add_route("/api/agent-card", api_agent_card, methods=["GET"])

        async def api_list_artifacts(request):
            """List metadata references available to a conversation/session."""
            conversation_id = str(request.path_params.get("conversation_id") or "")
            refs = [ref.to_dict() for ref in self.list_artifact_references(conversation_id)]
            return JSONResponse(
                {
                    "ok": True,
                    "conversation_id": conversation_id,
                    "count": len(refs),
                    "artifacts": refs,
                }
            )

        app.add_route("/api/artifacts/{conversation_id}", api_list_artifacts, methods=["GET"])

        # Optional subclass hook for custom routes/endpoints.
        self.configure_app(app)

        self._configure_auth(app)

        return app

    def run(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """
        Start the agent HTTP server.

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (default: from AGENT_PORT env var or 8000)
        """
        app = self.build_app(register_on_startup=True)

        # Start HTTP server
        if port is None:
            port = int(os.getenv("AGENT_PORT", "8000"))

        logger.info(f"Starting HTTP server on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
