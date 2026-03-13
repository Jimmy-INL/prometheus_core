"""
Thermal Analysis Agent - Specialist for nuclear reactor thermal analysis
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


class ThermalAnalysisAgent(PrometheusAgent):
    """Agent for thermal analysis."""

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Perform thermal analysis using Claude for expert assessment.

        Uses the Anthropic API to generate expert-level thermal analysis
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
                "analysis_type": "thermal",
                "error": "ANTHROPIC_API_KEY not configured",
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

        context_str = ""
        if operating_context:
            context_str = "\nOperating Conditions:\n"
            if operating_context.get("temperature_c"):
                context_str += f"- Temperature: {operating_context['temperature_c']}C\n"
            if operating_context.get("pressure_mpa"):
                context_str += f"- Pressure: {operating_context['pressure_mpa']} MPa\n"
            if operating_context.get("operating_hours"):
                context_str += f"- Operating Hours: {operating_context['operating_hours']}\n"

        prompt = f"""You are a nuclear reactor thermal analysis specialist. Analyze thermal effects on material: {material_id}
{context_str}
Provide a comprehensive thermal analysis as a JSON object with this structure:
{{
    "operating_temperature_c": <float>,
    "max_temperature_c": <float>,
    "min_temperature_c": <float>,
    "temperature_gradient_c_per_cm": <float>,
    "thermal_cycles_accumulated": <int>,
    "thermal_fatigue_usage_factor": <float 0-1>,
    "creep_strain_percent": <float>,
    "thermal_conductivity_degradation_percent": <float>,
    "thermal_stress_mpa": <float>,
    "cycle_categories": {{
        "startup_shutdown": <int>,
        "load_following": <int>,
        "thermal_transients": <int>
    }},
    "fatigue_analysis": {{
        "design_cycles": <int>,
        "accumulated_cycles": <int>,
        "remaining_cycles": <int>,
        "fatigue_curve": "<ASME reference>"
    }},
    "creep_analysis": {{
        "creep_rate_percent_per_hour": <scientific notation>,
        "larson_miller_parameter": <float>,
        "rupture_life_fraction_used": <float 0-1>,
        "tertiary_creep_onset": "<detected/not_detected>"
    }},
    "status": "<acceptable/degraded/critical>",
    "recommendations": [<list of recommendations>],
    "confidence": <float 0-1>
}}

Consider thermal fatigue, creep damage, thermal aging, and thermal stress per ASME Section III."""

        try:
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=2048,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(response_text)
            analysis["material_id"] = material_id
            analysis["timestamp"] = datetime.now(timezone.utc).isoformat()
            analysis["analysis_type"] = "thermal"
            analysis["model_used"] = MODEL_NAME

            return analysis

        except Exception as e:
            return {
                "material_id": material_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis_type": "thermal",
                "error": f"Analysis failed: {str(e)}",
            }


if __name__ == "__main__":
    agent = ThermalAnalysisAgent(agent_name="Thermal Analysis Agent")
    agent.run()
