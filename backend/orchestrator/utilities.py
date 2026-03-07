import asyncio
import logging
from datetime import datetime, timezone

from orchestrator.a2a_client import send_task, A2AError
from models.workflow import WorkflowStepDef

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workflow runner (async generator)
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _execute_step(step_def: WorkflowStepDef) -> str:
    """Run a single step — live A2A call if configured, otherwise canned response."""
    if step_def.a2a_endpoint:
        try:
            log.info("A2A call to %s for step '%s'", step_def.a2a_endpoint, step_def.name)
            response = await send_task(
                endpoint=step_def.a2a_endpoint,
                message=step_def.prompt,
                timeout=step_def.a2a_timeout,
                headers=step_def.a2a_headers,
            )
            log.info("A2A response received for step '%s'", step_def.name)
            return response
        except (A2AError, Exception) as exc:
            log.warning(
                "A2A call failed for step '%s': %s — falling back to canned response",
                step_def.name,
                exc,
            )
            return step_def.response
    else:
        # Canned mode: simulate processing time
        await asyncio.sleep(step_def.delay)
        return step_def.response

