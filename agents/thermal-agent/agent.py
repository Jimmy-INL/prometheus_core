"""
Thermal Analysis Agent - Specialist for nuclear reactor thermal analysis
Implements A2A protocol using prometheus_api with Bearer token authentication
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from anthropic import Anthropic
from prometheus_api.agent import MissingInput, PrometheusAgent
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")
THERMAL_ANALYSIS_JSON_TYPE = "prometheus.thermal_analysis.result.v1"


def _format_number(value: Any, suffix: str = "") -> str:
    if isinstance(value, bool) or value is None:
        return "not provided"
    if isinstance(value, int):
        return f"{value}{suffix}"
    if isinstance(value, float):
        if value != 0 and abs(value) < 0.001:
            return f"{value:.2e}{suffix}"
        if value.is_integer():
            return f"{int(value)}{suffix}"
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}" if suffix else str(value)


def _build_thermal_summary(material_id: str, analysis: Dict[str, Any]) -> str:
    status = str(analysis.get("status") or "completed").replace("_", " ")
    operating_temperature_c = analysis.get("operating_temperature_c")
    thermal_stress_mpa = analysis.get("thermal_stress_mpa")
    fatigue_usage = analysis.get("thermal_fatigue_usage_factor")

    parts: List[str] = [f"Thermal analysis for {material_id} completed."]
    if operating_temperature_c is not None:
        parts.append(f"Operating temperature: {_format_number(operating_temperature_c, ' C')}.")
    parts.append(f"Overall status: {status}.")
    if thermal_stress_mpa is not None:
        parts.append(f"Thermal stress: {_format_number(thermal_stress_mpa, ' MPa')}.")
    if fatigue_usage is not None:
        parts.append(f"Fatigue usage factor: {_format_number(fatigue_usage)}.")
    return " ".join(parts)


def _build_thermal_report(material_id: str, analysis: Dict[str, Any]) -> str:
    status = str(analysis.get("status") or "unknown").replace("_", " ")
    confidence = analysis.get("confidence")
    recommendations = analysis.get("recommendations") or []
    fatigue = analysis.get("fatigue_analysis") or {}
    creep = analysis.get("creep_analysis") or {}
    cycle_categories = analysis.get("cycle_categories") or {}

    lines = [
        f"Thermal Analysis for {material_id}",
        "",
        f"- Overall status: {status}",
        f"- Confidence: {_format_number(confidence)}",
        f"- Operating temperature: {_format_number(analysis.get('operating_temperature_c'), ' C')}",
        f"- Thermal stress: {_format_number(analysis.get('thermal_stress_mpa'), ' MPa')}",
        f"- Thermal fatigue usage factor: {_format_number(analysis.get('thermal_fatigue_usage_factor'))}",
        f"- Creep strain: {_format_number(analysis.get('creep_strain_percent'), ' %')}",
        f"- Thermal conductivity degradation: {_format_number(analysis.get('thermal_conductivity_degradation_percent'), ' %')}",
        "",
        "Cycle summary:",
        f"- Total thermal cycles: {_format_number(analysis.get('thermal_cycles_accumulated'))}",
        f"- Startup and shutdown cycles: {_format_number(cycle_categories.get('startup_shutdown'))}",
        f"- Load-following cycles: {_format_number(cycle_categories.get('load_following'))}",
        f"- Thermal transients: {_format_number(cycle_categories.get('thermal_transients'))}",
        "",
        "Fatigue analysis:",
        f"- Design cycles: {_format_number(fatigue.get('design_cycles'))}",
        f"- Accumulated cycles: {_format_number(fatigue.get('accumulated_cycles'))}",
        f"- Remaining cycles: {_format_number(fatigue.get('remaining_cycles'))}",
        f"- Fatigue curve: {fatigue.get('fatigue_curve') or 'not provided'}",
        "",
        "Creep analysis:",
        f"- Creep rate: {_format_number(creep.get('creep_rate_percent_per_hour'), ' %/hour')}",
        f"- Larson-Miller parameter: {_format_number(creep.get('larson_miller_parameter'))}",
        f"- Rupture life fraction used: {_format_number(creep.get('rupture_life_fraction_used'))}",
        f"- Tertiary creep onset: {creep.get('tertiary_creep_onset') or 'not provided'}",
    ]

    if recommendations:
        lines.extend(["", "Recommendations:"])
        for item in recommendations:
            lines.append(f"- {item}")

    return "\n".join(lines)


class ThermalAnalysisAgent(PrometheusAgent):
    """Agent for thermal analysis."""

    def _merge_resolved_inputs(self, resolved: Dict[str, Any], params: Dict[str, Any], context: RequestContext) -> Dict[str, Any]:
        merged = dict(resolved or {})
        if params.get("material_id"):
            merged["material_id"] = params["material_id"]

        operating_context = params.get("context", {})
        if isinstance(operating_context, dict):
            for key in ("temperature_c", "pressure_mpa", "operating_hours", "thermal_cycles"):
                if operating_context.get(key) is not None:
                    merged[key] = operating_context[key]

        for key, value in self.get_provided_inputs(context).items():
            if value is not None:
                merged[key] = value

        return merged

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
        state = self.load_context_state(str(context.context_id or ""))
        resolved = self._merge_resolved_inputs(state.get("resolved", {}), params, context)

        material_id = resolved.get("material_id")
        if not material_id:
            await self.send_input_required(
                context=context,
                event_queue=event_queue,
                missing_inputs=[
                    MissingInput(
                        name="material_id",
                        description="Canonical material identifier for the thermal analysis.",
                        user_prompt="Which material should I analyze thermally?",
                        type="string",
                        resolvable_from_context=True,
                    )
                ],
                hint="I need the target material before I can run the thermal analysis.",
            )
            self.save_context_state(
                str(context.context_id or ""),
                {
                    "resolved": resolved,
                    "pending": ["material_id"],
                    "task_id": context.task_id,
                },
            )
            return {"status": "input_required"}

        operating_context = {
            "temperature_c": resolved.get("temperature_c"),
            "pressure_mpa": resolved.get("pressure_mpa"),
            "operating_hours": resolved.get("operating_hours"),
            "thermal_cycles": resolved.get("thermal_cycles"),
        }

        if operating_context.get("temperature_c") is None:
            await self.send_input_required(
                context=context,
                event_queue=event_queue,
                missing_inputs=[
                    MissingInput(
                        name="temperature_c",
                        description="Operating temperature in Celsius at which the material should be evaluated.",
                        user_prompt="What operating temperature should I use for the thermal analysis (in Celsius)?",
                        type="number",
                        resolvable_from_context=True,
                    )
                ],
                hint="Thermal analysis requires an operating temperature before it can proceed.",
            )
            self.save_context_state(
                str(context.context_id or ""),
                {
                    "resolved": resolved,
                    "pending": ["temperature_c"],
                    "task_id": context.task_id,
                },
            )
            return {"status": "input_required"}

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
            analysis["operating_temperature_c"] = operating_context.get(
                "temperature_c",
                analysis.get("operating_temperature_c"),
            )
            if operating_context.get("pressure_mpa") is not None:
                analysis["pressure_mpa"] = operating_context["pressure_mpa"]
            if operating_context.get("operating_hours") is not None:
                analysis["operating_hours"] = operating_context["operating_hours"]
            if operating_context.get("thermal_cycles") is not None:
                analysis["thermal_cycles_input"] = operating_context["thermal_cycles"]

            message = _build_thermal_summary(material_id, analysis)
            report = _build_thermal_report(material_id, analysis)

            await self.send_json_artifact(
                context=context,
                event_queue=event_queue,
                payload=analysis,
                name=f"{material_id.lower()}_thermal_analysis",
                description=f"Thermal analysis result for {material_id}.",
                json_type=THERMAL_ANALYSIS_JSON_TYPE,
                catalog_artifact=True,
            )

            self.save_context_state(
                str(context.context_id or ""),
                {
                    "resolved": resolved,
                    "pending": [],
                    "task_id": context.task_id,
                    "last_result_timestamp": analysis["timestamp"],
                },
            )

            return {
                **analysis,
                "message": message,
                "report": report,
            }

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
