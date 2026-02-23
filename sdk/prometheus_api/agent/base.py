"""
PrometheusAgent - Base class for A2A agents with built-in authentication and registry support.

This module provides a base class that handles all the boilerplate for creating
A2A-enabled agents, allowing you to focus on your agent's core logic.
"""

import os
import sys
import json
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from starlette.responses import JSONResponse

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Artifact,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from .middleware import BearerTokenMiddleware
import uvicorn
import httpx

logger = logging.getLogger(__name__)


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

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Execute the agent task.

        This method handles the standard A2A execution flow:
        1. Extract parameters from message
        2. Send "working" status
        3. Call _execute() (implemented by subclass)
        4. Send completion status and artifact
        5. Handle errors

        Args:
            context: A2A request context containing the message and parameters
            event_queue: Queue for sending status updates
        """
        try:
            logger.info(f"Starting {self.agent_name} execution")

            # Extract parameters from the message
            params = self._extract_params(context)

            # Send "working" status
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    final=False,
                    status=TaskStatus(state=TaskState.working),
                )
            )

            # Perform the main analysis (implemented by subclass)
            result = await self._execute(params, context, event_queue)

            # Send result as artifact BEFORE marking task complete
            # (Otherwise the response may be returned before artifact is included)
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    artifact=Artifact(
                        artifactId=str(uuid.uuid4()),
                        name="result",
                        parts=[TextPart(text=json.dumps(result, indent=2))],
                    ),
                )
            )

            # Send completion status (must come after artifact)
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    final=True,
                    status=TaskStatus(state=TaskState.completed),
                )
            )

            logger.info(f"{self.agent_name} execution completed successfully")

        except Exception as e:
            logger.error(f"Error during execution: {str(e)}", exc_info=True)
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=context.task_id,
                    contextId=context.context_id,
                    final=True,
                    status=TaskStatus(state=TaskState.failed),
                )
            )
            raise

    def _extract_params(self, context: RequestContext) -> Dict[str, Any]:
        """
        Extract parameters from the A2A message context.

        Args:
            context: A2A request context

        Returns:
            Dict of extracted parameters

        Raises:
            ValueError: If message format is invalid
        """
        # Get user input text from the context
        text = context.get_user_input()

        if not text:
            # Return empty params if no text
            return {}

        try:
            params = json.loads(text)
        except json.JSONDecodeError:
            # If not valid JSON, treat the text as a plain message
            logger.debug(f"Message is not JSON, treating as plain text: {text}")
            params = {"message": text}

        logger.info(f"Extracted parameters: {params}")
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

                # Send progress update
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        taskId=context.task_id,
                        contextId=context.context_id,
                        final=False,
                        status=TaskStatus(state=TaskState.working),
                    )
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

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Handle task cancellation.

        Args:
            context: A2A request context
            event_queue: Queue for sending status updates
        """
        logger.info(f"Cancellation requested for {self.agent_name}")
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                final=True,
                status=TaskStatus(state=TaskState.canceled),
            )
        )


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

    def __init__(
        self,
        agent_name: str = "Agent",
        agent_card_path: Optional[str] = None
    ):
        """
        Initialize the Prometheus agent.

        Args:
            agent_name: Name of the agent (for logging and metadata)
            agent_card_path: Path to agent_card.json (defaults to ./agent_card.json)
        """
        self.agent_name = agent_name
        self.agent_card_path = agent_card_path or "agent_card.json"

        # Will be set during initialization
        self.agent_card = None
        self.agent_card_dict = None  # Raw dict for registry registration
        self.executor = None

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
            if hasattr(__main__, '__file__'):
                script_dir = Path(__main__.__file__).parent
                agent_card_path = script_dir / agent_card_path

        try:
            with open(agent_card_path, 'r') as f:
                agent_card_dict = json.load(f)
        except FileNotFoundError:
            logger.error(f"agent_card.json not found at {agent_card_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in agent_card.json: {e}")
            raise

        # Override URL with environment configuration
        port = os.getenv('AGENT_PORT', '8000')
        host = os.getenv('AGENT_HOST', 'localhost')
        agent_card_dict['url'] = f"http://{host}:{port}"

        # Store the raw dict for registry registration
        self.agent_card_dict = agent_card_dict

        # Convert capabilities dict to AgentCapabilities object
        capabilities_dict = agent_card_dict.get('capabilities', {})
        capabilities = AgentCapabilities(
            streaming=capabilities_dict.get('streaming', False),
            pushNotifications=capabilities_dict.get('pushNotifications', False),
        )

        # Convert skills list to AgentSkill objects
        skills = [
            AgentSkill(
                id=skill['id'],
                name=skill['name'],
                description=skill.get('description', ''),
                tags=skill.get('tags', []),
            )
            for skill in agent_card_dict.get('skills', [])
        ]

        # Create the AgentCard object
        agent_card = AgentCard(
            name=agent_card_dict['name'],
            description=agent_card_dict['description'],
            url=agent_card_dict['url'],
            version=agent_card_dict.get('version', '1.0.0'),
            capabilities=capabilities,
            skills=skills,
            defaultInputModes=agent_card_dict.get('defaultInputModes', ['text']),
            defaultOutputModes=agent_card_dict.get('defaultOutputModes', ['text']),
        )

        logger.info(f"Loaded agent card: {agent_card.name} v{agent_card.version}")
        logger.info(f"Agent URL: {agent_card.url}")

        return agent_card

    def register_with_registry(self, agent_card: AgentCard) -> None:
        """
        Register this agent with the registry service.

        Args:
            agent_card: The AgentCard to register
        """
        registry_url = os.getenv("REGISTRY_URL")
        if not registry_url:
            logger.info("REGISTRY_URL not set - skipping registry registration")
            return

        agent_secret = os.getenv("AGENT_SECRET")

        headers = {}
        if agent_secret:
            headers["Authorization"] = f"Bearer {agent_secret}"

        # Convert AgentCard to registry format (which differs from A2A AgentCard)
        # Registry expects: agent_id, name, description, url, capabilities (list of strings), version
        # Also include full agent_card dict for dynamic tool discovery
        registration_data = {
            "agent_id": agent_card.name.lower().replace(" ", "-"),
            "name": agent_card.name,
            "description": agent_card.description,
            "url": agent_card.url,
            "capabilities": [skill.id for skill in agent_card.skills],
            "version": agent_card.version,
            "agent_card": getattr(self, 'agent_card_dict', None),  # Full agent card for tool discovery
        }

        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                response = client.post(
                    f"{registry_url}/agents/register",
                    json=registration_data
                )
                response.raise_for_status()
                logger.info(f"Successfully registered with registry at {registry_url}")
        except Exception as e:
            logger.error(f"Failed to register with registry: {str(e)}")
            logger.warning("Continuing without registry registration")

    def create_executor(self) -> PrometheusAgentExecutor:
        """
        Create the agent executor.

        Override this method if you need custom executor initialization.

        Returns:
            Agent executor instance
        """
        # Create a custom executor class that wraps _execute
        agent_instance = self

        class CustomExecutor(PrometheusAgentExecutor):
            async def _execute(
                self,
                params: Dict[str, Any],
                context: RequestContext,
                event_queue: EventQueue,
            ) -> Dict[str, Any]:
                """Delegate to the agent instance's _execute method."""
                return await agent_instance._execute(params, context, event_queue)

        return CustomExecutor(agent_name=self.agent_name)

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

                # Send progress update
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        taskId=context.task_id,
                        contextId=context.context_id,
                        final=False,
                        status=TaskStatus(state=TaskState.working),
                    )
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

    def run(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """
        Start the agent HTTP server.

        This method:
        1. Loads the agent card
        2. Creates the executor
        3. Sets up the HTTP server with A2A protocol
        4. Adds Bearer token authentication
        5. Registers with the registry
        6. Starts the server

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (default: from AGENT_PORT env var or 8000)
        """
        logger.info(f"Starting {self.agent_name}")

        # Load agent card
        self.agent_card = self.load_agent_card()

        # Create executor
        self.executor = self.create_executor()

        # Create request handler
        request_handler = DefaultRequestHandler(
            agent_executor=self.executor,
            task_store=InMemoryTaskStore()
        )

        # Create A2A application builder
        builder = A2AStarletteApplication(
            agent_card=self.agent_card,
            http_handler=request_handler
        )

        # Build the Starlette app
        app = builder.build()

        # add health endpoint
        app.add_route("/health", lambda request: JSONResponse({"ok": True}), methods=["GET"])

        # Add Bearer token authentication middleware
        agent_secret = os.getenv("AGENT_SECRET")
        agent_secret_required = os.getenv("AGENT_SECRET_REQUIRED", "true").lower() in ["true", "1", "yes"]

        if agent_secret or agent_secret_required:
            app.add_middleware(BearerTokenMiddleware, secret=agent_secret, required=agent_secret_required)
            if agent_secret:
                logger.info("Bearer token authentication enabled")
            else:
                logger.warning("AGENT_SECRET_REQUIRED=true but AGENT_SECRET not set - authentication disabled")
        else:
            logger.warning("Bearer token authentication disabled (AGENT_SECRET_REQUIRED=false)")

        # Register with registry
        self.register_with_registry(self.agent_card)

        # Start HTTP server
        if port is None:
            port = int(os.getenv("AGENT_PORT", "8000"))

        logger.info(f"Starting HTTP server on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
