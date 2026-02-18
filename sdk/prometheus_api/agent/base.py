"""
PrometheusAgent - Base class for A2A agents with built-in authentication and registry support.

This module provides a base class that handles all the boilerplate for creating
A2A-enabled agents, allowing you to focus on your agent's core logic.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from .middleware import BearerTokenMiddleware
import uvicorn
import httpx

logger = logging.getLogger(__name__)


class PrometheusAgentExecutor(AgentExecutor):
    """
    Base executor for Prometheus agents.

    Handles parameter extraction, status updates, and error handling.
    Subclasses only need to implement process_analysis().
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

    def execute(self, context: Dict[str, Any], event_queue) -> Dict[str, Any]:
        """
        Execute the agent task.

        This method handles the standard A2A execution flow:
        1. Extract parameters from message
        2. Send "working" status
        3. Call process_analysis() (implemented by subclass)
        4. Send completion status and artifact
        5. Handle errors

        Args:
            context: A2A context containing the message and parameters
            event_queue: Queue for sending status updates

        Returns:
            Dict containing the analysis results
        """
        try:
            logger.info(f"Starting {self.agent_name} execution")

            # Extract parameters from the message
            params = self._extract_params(context)

            # Send "working" status
            event_queue.put({
                "type": "status",
                "status": "working",
                "message": "Processing request..."
            })

            # Perform the main analysis (implemented by subclass)
            result = self.process_analysis(params, event_queue)

            # Send completion status
            event_queue.put({
                "type": "status",
                "status": "completed",
                "message": "Analysis complete"
            })

            # Send result as artifact
            event_queue.put({
                "type": "artifact",
                "data": json.dumps(result, indent=2)
            })

            logger.info(f"{self.agent_name} execution completed successfully")
            return result

        except Exception as e:
            logger.error(f"Error during execution: {str(e)}", exc_info=True)
            event_queue.put({
                "type": "status",
                "status": "failed",
                "message": f"Error: {str(e)}"
            })
            raise

    def _extract_params(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract parameters from the A2A message context.

        Args:
            context: A2A context

        Returns:
            Dict of extracted parameters

        Raises:
            ValueError: If message format is invalid
        """
        message = context.get("message", {})
        parts = message.get("parts", [])

        if not parts:
            raise ValueError("No message parts found")

        # Extract text from first part
        text = parts[0].get("text", "{}")

        try:
            params = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message as JSON: {text}")
            raise ValueError(f"Invalid JSON in message: {str(e)}")

        logger.info(f"Extracted parameters: {params}")
        return params

    def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
        """
        Process the analysis request.

        OVERRIDE THIS METHOD in your agent subclass to implement your agent's logic.

        Args:
            params: Parameters extracted from the A2A message
            event_queue: Queue for sending progress updates

        Returns:
            Dict containing the analysis results

        Example:
            ```python
            def process_analysis(self, params, event_queue):
                input_data = params.get("input_data")

                # Send progress update
                event_queue.put({
                    "type": "status",
                    "status": "working",
                    "message": "Processing data..."
                })

                # Do your work
                result = do_something(input_data)

                return {
                    "status": "success",
                    "result": result
                }
            ```
        """
        raise NotImplementedError(
            "Subclasses must implement process_analysis() method. "
            "This is where your agent's core logic should go."
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
    2. Override process_analysis() method
    3. Call run()

    Example:
        ```python
        from prometheus_api.agent import PrometheusAgent

        class MyAgent(PrometheusAgent):
            def process_analysis(self, params, event_queue):
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
        self.executor = None

    def load_agent_card(self) -> Dict[str, Any]:
        """
        Load the agent card from JSON file and update URL from environment.

        Returns:
            Dict representing the agent card with runtime URL

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
                agent_card = json.load(f)
        except FileNotFoundError:
            logger.error(f"agent_card.json not found at {agent_card_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in agent_card.json: {e}")
            raise

        # Override URL with environment configuration
        port = os.getenv('AGENT_PORT', '8000')
        host = os.getenv('AGENT_HOST', 'localhost')
        agent_card['url'] = f"http://{host}:{port}"

        logger.info(f"Loaded agent card: {agent_card['name']} v{agent_card['version']}")
        logger.info(f"Agent URL: {agent_card['url']}")

        return agent_card

    def register_with_registry(self, agent_card: Dict[str, Any]) -> None:
        """
        Register this agent with the registry service.

        Args:
            agent_card: The agent card to register
        """
        registry_url = os.getenv("REGISTRY_URL")
        if not registry_url:
            logger.info("REGISTRY_URL not set - skipping registry registration")
            return

        agent_secret = os.getenv("AGENT_SECRET")

        headers = {}
        if agent_secret:
            headers["Authorization"] = f"Bearer {agent_secret}"

        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                response = client.post(
                    f"{registry_url}/agents/register",
                    json=agent_card
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
        # Create a custom executor class that wraps process_analysis
        agent_instance = self

        class CustomExecutor(PrometheusAgentExecutor):
            def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
                """Delegate to the agent instance's process_analysis method."""
                return agent_instance.process_analysis(params, event_queue)

        return CustomExecutor(agent_name=self.agent_name)

    def process_analysis(self, params: Dict[str, Any], event_queue) -> Dict[str, Any]:
        """
        Process the analysis request.

        OVERRIDE THIS METHOD to implement your agent's logic.

        Args:
            params: Parameters extracted from the A2A message
            event_queue: Queue for sending progress updates

        Returns:
            Dict containing the analysis results

        Example:
            ```python
            def process_analysis(self, params, event_queue):
                input_data = params.get("input_data")

                # Send progress update
                event_queue.put({
                    "type": "status",
                    "status": "working",
                    "message": "Processing..."
                })

                # Your logic here
                result = do_work(input_data)

                return {"status": "success", "result": result}
            ```
        """
        raise NotImplementedError(
            "You must override process_analysis() in your agent subclass. "
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
