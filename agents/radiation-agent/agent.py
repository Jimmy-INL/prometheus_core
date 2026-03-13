"""
Radiation Damage Agent - Specialist for nuclear reactor radiation damage analysis
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


class RadiationDamageAgent(PrometheusAgent):
    """Agent for radiation damage analysis."""

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Perform radiation damage analysis using Claude for expert assessment.

        Uses the Anthropic API to generate expert-level radiation damage analysis
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
                "analysis_type": "radiation_damage",
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

        # Build context for Claude
        context_str = ""
        if operating_context:
            context_str = "\nOperating Conditions:\n"
            if operating_context.get("temperature_c"):
                context_str += f"- Temperature: {operating_context['temperature_c']}C\n"
            if operating_context.get("pressure_mpa"):
                context_str += f"- Pressure: {operating_context['pressure_mpa']} MPa\n"
            if operating_context.get("operating_hours"):
                context_str += f"- Operating Hours: {operating_context['operating_hours']}\n"

        prompt = f"""You are a nuclear reactor radiation damage specialist. Analyze radiation-induced damage for material: {material_id}
{context_str}
Provide a comprehensive radiation damage analysis as a JSON object with this structure:
{{
    "total_fluence_n_cm2": <scientific notation as float>,
    "dpa": <float, displacements per atom>,
    "dbtt_shift_c": <float, ductile-to-brittle transition temperature shift in Celsius>,
    "void_swelling_percent": <float>,
    "helium_concentration_appm": <float, atomic parts per million>,
    "hydrogen_concentration_appm": <float>,
    "fluence_spectrum": {{
        "thermal": <float>,
        "epithermal": <float>,
        "fast": <float>
    }},
    "damage_mechanisms": [<list of active damage mechanisms>],
    "structural_integrity": "<acceptable/degraded/critical>",
    "remaining_service_life_years": <float>,
    "surveillance_capsule_data": {{
        "capsules_remaining": <int>,
        "next_withdrawal_date": "<ISO date>"
    }},
    "recommendations": [<list of specific recommendations>],
    "regulatory_compliance": {{
        "regulatory_limit_dbtt_c": 93.3,
        "margin_to_limit_c": <float>,
        "status": "<within_limits/approaching_limit/exceeds_limit>"
    }},
    "confidence": <float 0-1>
}}

Consider neutron embrittlement, void swelling, helium embrittlement, and transmutation effects. Follow 10 CFR 50.61 regulatory limits."""

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
            analysis["analysis_type"] = "radiation_damage"
            analysis["model_used"] = MODEL_NAME

            return analysis

        except Exception as e:
            return {
                "material_id": material_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis_type": "radiation_damage",
                "error": f"Analysis failed: {str(e)}",
            }


if __name__ == "__main__":
    agent = RadiationDamageAgent(agent_name="Radiation Damage Analysis Agent")
    agent.run()
