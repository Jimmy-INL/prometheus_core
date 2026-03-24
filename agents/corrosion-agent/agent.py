"""
Corrosion Analysis Agent - Specialist for nuclear reactor corrosion analysis
Implements A2A protocol using prometheus_api with Bearer token authentication
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from anthropic import Anthropic
from prometheus_api.agent import PrometheusAgent
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")


class CorrosionAnalysisAgent(PrometheusAgent):
    """Agent for corrosion analysis."""

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Perform corrosion analysis on the specified material using Claude.

        Uses the Anthropic API to generate expert-level corrosion analysis
        based on material properties and operating conditions.
        """
        material_id = params.get("material_id")
        operating_context = params.get("context", {})

        if not material_id:
            return {"error": "material_id is required"}

        if not ANTHROPIC_API_KEY:
            return {
                "material_id": material_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis_type": "corrosion",
                "error": "ANTHROPIC_API_KEY not configured",
                "note": "API integration required for intelligent analysis",
            }

        # Send status update
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=context.task_id,
                contextId=context.context_id,
                final=False,
                status=TaskStatus(state=TaskState.working),
            )
        )

        # Build context for Claude
        context_str = ""
        if operating_context:
            context_str = "\nOperating Conditions:\n"
            if operating_context.get("temperature_c"):
                context_str += f"- Temperature: {operating_context['temperature_c']}C\n"
            if operating_context.get("pressure_mpa"):
                context_str += f"- Pressure: {operating_context['pressure_mpa']} MPa\n"
            if operating_context.get("coolant_chemistry"):
                context_str += f"- Coolant Chemistry: {json.dumps(operating_context['coolant_chemistry'])}\n"
            if operating_context.get("operating_hours"):
                context_str += f"- Operating Hours: {operating_context['operating_hours']}\n"

        prompt = f"""You are a nuclear reactor corrosion specialist. Analyze the corrosion state of material: {material_id}
{context_str}
Provide a comprehensive corrosion analysis as a JSON object with the following structure:
{{
    "oxidation_rate_mm_per_year": <float>,
    "pitting_index": <float 0-1>,
    "scc_susceptibility": "<low/medium/high>",
    "coating_status": "<intact/degraded/failed>",
    "environmental_factors": {{
        "ph_level": <float>,
        "dissolved_oxygen_ppb": <float>,
        "chloride_concentration_ppm": <float>
    }},
    "corrosion_mechanisms": [<list of active mechanisms>],
    "affected_area_percent": <float>,
    "recommendations": [<list of actionable recommendations>],
    "risk_level": "<low/medium/high/critical>",
    "confidence": <float 0-1>
}}

Focus on realistic nuclear reactor corrosion scenarios. Consider general corrosion, pitting, stress corrosion cracking (SCC), flow-accelerated corrosion, and intergranular attack."""

        try:
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=2048,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            # Extract JSON from response
            response_text = response.content[0].text
            # Try to extract JSON from markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(response_text)

            # Add metadata
            analysis["material_id"] = material_id
            analysis["timestamp"] = datetime.now(timezone.utc).isoformat()
            analysis["analysis_type"] = "corrosion"
            analysis["model_used"] = MODEL_NAME

            return analysis

        except Exception as e:
            return {
                "material_id": material_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis_type": "corrosion",
                "error": f"Analysis failed: {str(e)}",
            }


if __name__ == "__main__":
    agent = CorrosionAnalysisAgent(agent_name="Corrosion Analysis Agent")
    agent.run()
