"""
TEMPLATE_NAME Agent - A2A Agent Template

This is a template for creating A2A-enabled agents. Replace TEMPLATE_NAME with your agent's name.
"""

import sys
import logging
from typing import Dict, Any
from datetime import datetime

from prometheus_api.agent import (
    PrometheusAgent,
    RequestContext,
    EventQueue,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from prometheus_api.storage_client import StorageClient  # Example - use as needed

# Add shared directory to path
sys.path.insert(0, "/app")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TEMPLATE_CLASSAgent(PrometheusAgent):
    """
    TEMPLATE_NAME Agent.

    This agent handles [DESCRIBE YOUR AGENT'S CAPABILITIES HERE].
    """

    async def process_analysis(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Process the analysis request.

        This is the main method you should customize for your agent's specific logic.

        Args:
            params: Parameters extracted from the A2A message
            context: A2A request context with task_id and context_id
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
        # Example: Use storage_client to process the data
        # result = StorageClient().items.get(input_data)

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
        # import asyncio
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
        #     # Send progress update using A2A event types
        #     await event_queue.enqueue_event(
        #         TaskStatusUpdateEvent(
        #             taskId=context.task_id,
        #             contextId=context.context_id,
        #             final=False,
        #             status=TaskStatus(state=TaskState.working),
        #         )
        #     )
        #
        #     # Simulate work (replace with actual processing)
        #     await asyncio.sleep(1)
        #     results[step] = f"Completed {step}"
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


if __name__ == "__main__":
    # Create and run the agent
    agent = TEMPLATE_CLASSAgent(agent_name="TEMPLATE_NAME Agent")
    agent.run()
