"""
Corrosion Analysis Agent - Specialist for nuclear reactor corrosion analysis
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
CORROSION_ANALYSIS_JSON_TYPE = "prometheus.corrosion_analysis.result.v1"

ANALYSIS_PROMPT_TEMPLATE = """\
You are a nuclear reactor corrosion specialist. Analyze the corrosion state of material: {material_id}
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


def _build_corrosion_summary(material_id: str, analysis: Dict[str, Any]) -> str:
    risk_level = str(analysis.get("risk_level") or "unknown")
    oxidation_rate = analysis.get("oxidation_rate_mm_per_year")
    pitting_index = analysis.get("pitting_index")

    parts: List[str] = [f"Corrosion analysis for {material_id} completed."]
    if oxidation_rate is not None:
        parts.append(f"Oxidation rate: {oxidation_rate:.4f} mm/year.")
    if pitting_index is not None:
        parts.append(f"Pitting index: {pitting_index:.2f}.")
    parts.append(f"Risk level: {risk_level}.")
    return " ".join(parts)


def _build_corrosion_report(material_id: str, analysis: Dict[str, Any]) -> str:
    risk_level = str(analysis.get("risk_level") or "unknown")
    confidence = analysis.get("confidence")
    scc = analysis.get("scc_susceptibility") or "not provided"
    coating = analysis.get("coating_status") or "not provided"
    recommendations = analysis.get("recommendations") or []
    mechanisms = analysis.get("corrosion_mechanisms") or []
    env = analysis.get("environmental_factors") or {}

    lines = [
        f"Corrosion Analysis for {material_id}",
        "",
        f"- Risk level: {risk_level}",
        f"- Confidence: {confidence}",
        f"- Oxidation rate: {analysis.get('oxidation_rate_mm_per_year')} mm/year",
        f"- Pitting index: {analysis.get('pitting_index')}",
        f"- SCC susceptibility: {scc}",
        f"- Coating status: {coating}",
        f"- Affected area: {analysis.get('affected_area_percent')} %",
        "",
        "Environmental factors:",
        f"- pH level: {env.get('ph_level')}",
        f"- Dissolved oxygen: {env.get('dissolved_oxygen_ppb')} ppb",
        f"- Chloride concentration: {env.get('chloride_concentration_ppm')} ppm",
    ]

    if mechanisms:
        lines.extend(["", "Active corrosion mechanisms:"])
        for m in mechanisms:
            lines.append(f"- {m}")

    if recommendations:
        lines.extend(["", "Recommendations:"])
        for item in recommendations:
            lines.append(f"- {item}")

    return "\n".join(lines)


class CorrosionAnalysisAgent(PrometheusAgent):
    """Agent for corrosion analysis."""

    def _merge_resolved_inputs(self, resolved: Dict[str, Any], params: Dict[str, Any], context: RequestContext) -> Dict[str, Any]:
        merged = dict(resolved or {})
        if params.get("material_id"):
            merged["material_id"] = params["material_id"]

        operating_context = params.get("context", {})
        if isinstance(operating_context, dict):
            for key in ("temperature_c", "pressure_mpa", "operating_hours", "coolant_chemistry"):
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
        Perform corrosion analysis on the specified material using Claude.

        Uses the Anthropic API to generate expert-level corrosion analysis
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
                        description="Canonical material identifier for the corrosion analysis.",
                        user_prompt="Which material should I analyze for corrosion?",
                        type="string",
                        resolvable_from_context=True,
                    )
                ],
                hint="I need the target material before I can run the corrosion analysis.",
            )
            self.save_context_state(
                str(context.context_id or ""),
                {
                    "resolved": resolved,
                    "pending": ["material_id"],
                    "task_id": context.task_id,
                },
            )
            return {}

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

        operating_context = {
            "temperature_c": resolved.get("temperature_c"),
            "pressure_mpa": resolved.get("pressure_mpa"),
            "operating_hours": resolved.get("operating_hours"),
            "coolant_chemistry": resolved.get("coolant_chemistry"),
        }

        # Build context for Claude
        context_str = ""
        non_null = {k: v for k, v in operating_context.items() if v is not None}
        if non_null:
            context_str = "\nOperating Conditions:\n"
            if non_null.get("temperature_c"):
                context_str += f"- Temperature: {non_null['temperature_c']}C\n"
            if non_null.get("pressure_mpa"):
                context_str += f"- Pressure: {non_null['pressure_mpa']} MPa\n"
            if non_null.get("coolant_chemistry"):
                context_str += f"- Coolant Chemistry: {json.dumps(non_null['coolant_chemistry'])}\n"
            if non_null.get("operating_hours"):
                context_str += f"- Operating Hours: {non_null['operating_hours']}\n"

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(material_id=material_id, context_str=context_str)

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

            message = _build_corrosion_summary(material_id, analysis)
            report = _build_corrosion_report(material_id, analysis)

            await self.send_json_artifact(
                context=context,
                event_queue=event_queue,
                payload=analysis,
                name=f"{material_id.lower()}_corrosion_analysis",
                description=f"Corrosion analysis result for {material_id}.",
                json_type=CORROSION_ANALYSIS_JSON_TYPE,
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
                "analysis_type": "corrosion",
                "error": f"Analysis failed: {str(e)}",
            }


if __name__ == "__main__":
    agent = CorrosionAnalysisAgent(agent_name="Corrosion Analysis Agent")
    agent.run()
