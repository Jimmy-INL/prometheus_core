"""
TEMPLATE_NAME Agent - A2A Agent Template

This is a template for creating A2A-enabled agents. Replace TEMPLATE_NAME with your agent's name.
"""

import os
import sys
import json
import logging
from typing import Dict, Any
from datetime import datetime

from a2a_sdk import AgentExecutor
import prometheus_api

# Add shared directory to path
sys.path.insert(0, "/app")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TEMPLATE_CLASSExecutor(AgentExecutor):
    """
    Executor for TEMPLATE_NAME Agent.

    This agent handles [DESCRIBE YOUR AGENT'S CAPABILITIES HERE].
    """

    def __init__(self):
        """Initialize the agent executor."""
        super().__init__()
        logger.info("Initialized TEMPLATE_NAME Agent")

    def execute(self, context: Dict[str, Any], event_queue) -> Dict[str, Any]:
        """
        Execute the agent task.

        Args:
            context: A2A context containing the message and parameters
            event_queue: Queue for sending status updates

        Returns:
            Dict containing the analysis results
        """
        try:
            logger.info("Starting TEMPLATE_NAME Agent execution")

            # Extract parameters from the message
            params = self._extract_params(context)

            # Send "working" status
            event_queue.put({
                "type": "status",
                "status": "working",
                "message": "Processing request..."
            })

            # Perform the main analysis (pass event_queue for progress updates)
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

            logger.info("TEMPLATE_NAME Agent execution completed successfully")
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

        This is the main method you should customize for your agent's specific logic.

        Args:
            params: Parameters extracted from the A2A message
            event_queue: Queue for sending progress updates

        Returns:
            Dict containing the analysis results
        """
        # Extract required parameters
        # Customize these based on your agent's needs
        input_data = params.get("input_data")
        if not input_data:
            raise ValueError("input_data parameter is required")

        # ============================================================
        # CUSTOMIZE THIS SECTION FOR YOUR AGENT'S LOGIC
        # ============================================================
        # Example: Use prometheus_api to process the data
        # result = prometheus_api.some_function(input_data)

        # For now, return a placeholder result
        result = {
            "status": "success",
            "input_received": input_data,
            "message": "Replace this with your agent's processing logic"
        }

        # You can access other parameters from params
        # optional_param = params.get("optional_param", "default_value")
        # ============================================================

        # ============================================================
        # LONG-RUNNING TASK EXAMPLE WITH PROGRESS UPDATES
        # ============================================================
        # Uncomment this section for an example of a long-running task
        # with incremental progress updates
        #
        # import time
        #
        # steps = [
        #     "Loading data",
        #     "Preprocessing",
        #     "Running analysis",
        #     "Generating results",
        #     "Finalizing"
        # ]
        #
        # results = {}
        # for i, step in enumerate(steps):
        #     # Send progress update
        #     progress = (i + 1) / len(steps) * 100
        #     event_queue.put({
        #         "type": "status",
        #         "status": "working",
        #         "message": f"{step}... ({progress:.0f}% complete)"
        #     })
        #
        #     # Simulate work (replace with actual processing)
        #     time.sleep(1)
        #     results[step] = f"Completed {step}"
        #
        #     # Optional: Send intermediate results as artifacts
        #     if i == 2:  # After "Running analysis"
        #         event_queue.put({
        #             "type": "artifact",
        #             "data": json.dumps({
        #                 "intermediate_result": "Analysis complete",
        #                 "progress": f"{progress:.0f}%"
        #             }, indent=2)
        #         })
        #
        # result = {
        #     "status": "success",
        #     "steps_completed": results,
        #     "total_steps": len(steps)
        # }
        # ============================================================

        # Add metadata
        result.update({
            "agent": "TEMPLATE_NAME",
            "timestamp": datetime.utcnow().isoformat()
        })

        return result


def create_agent_card() -> Dict[str, Any]:
    """
    Load the agent card from agent_card.json and update URL from environment.

    The agent card is loaded from the JSON file to serve as a single source of truth
    for agent metadata, capabilities, and skills. The URL is then updated based on
    environment variables to match the actual runtime configuration.

    Returns:
        Dict representing the agent card with runtime URL
    """
    # Load agent card from JSON file
    agent_card_path = os.path.join(os.path.dirname(__file__), "agent_card.json")

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
    # This ensures the agent advertises the correct URL regardless of deployment
    port = os.getenv('AGENT_PORT', '8000')
    host = os.getenv('AGENT_HOST', 'localhost')
    agent_card['url'] = f"http://{host}:{port}"

    logger.info(f"Loaded agent card: {agent_card['name']} v{agent_card['version']}")
    logger.info(f"Agent URL: {agent_card['url']}")

    return agent_card


def register_with_registry(agent_card: Dict[str, Any]) -> None:
    """
    Register this agent with the registry service.

    Args:
        agent_card: The agent card to register
    """
    import httpx

    registry_url = os.getenv("REGISTRY_URL", "http://registry:8000")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{registry_url}/agents/register",
                json=agent_card
            )
            response.raise_for_status()
            logger.info(f"Successfully registered with registry at {registry_url}")
    except Exception as e:
        logger.error(f"Failed to register with registry: {str(e)}")
        # Don't fail startup if registry is unavailable
        logger.warning("Continuing without registry registration")


def main():
    """Main entry point for the agent."""
    from a2a_sdk.http_server import start_http_server

    logger.info("Starting TEMPLATE_NAME Agent")

    # Create agent card
    agent_card = create_agent_card()

    # Create executor
    executor = TEMPLATE_CLASSExecutor()

    # Register with registry
    register_with_registry(agent_card)

    # Start HTTP server
    port = int(os.getenv("AGENT_PORT", "8000"))
    logger.info(f"Starting HTTP server on port {port}")

    start_http_server(
        executor=executor,
        agent_card=agent_card,
        port=port,
        host="0.0.0.0"
    )


if __name__ == "__main__":
    main()
