"""
Radiation Damage Agent - Specialist for nuclear reactor radiation damage analysis
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

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-6")
RADIATION_DAMAGE_JSON_TYPE = "prometheus.radiation_damage.result.v1"

ANALYSIS_PROMPT_TEMPLATE = """\
You are a nuclear reactor radiation damage specialist. Analyze radiation-induced damage for material: {material_id}
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


def _build_radiation_summary(material_id: str, analysis: Dict[str, Any]) -> str:
    integrity = str(analysis.get("structural_integrity") or "unknown")
    dpa = analysis.get("dpa")
    remaining_life = analysis.get("remaining_service_life_years")

    parts: List[str] = [f"Radiation damage analysis for {material_id} completed."]
    if dpa is not None:
        parts.append(f"Accumulated DPA: {dpa:.2f}.")
    if remaining_life is not None:
        parts.append(f"Estimated remaining service life: {remaining_life:.1f} years.")
    parts.append(f"Structural integrity: {integrity}.")
    return " ".join(parts)


def _build_radiation_report(material_id: str, analysis: Dict[str, Any]) -> str:
    integrity = str(analysis.get("structural_integrity") or "unknown")
    confidence = analysis.get("confidence")
    mechanisms = analysis.get("damage_mechanisms") or []
    recommendations = analysis.get("recommendations") or []
    fluence_spectrum = analysis.get("fluence_spectrum") or {}
    surveillance = analysis.get("surveillance_capsule_data") or {}
    regulatory = analysis.get("regulatory_compliance") or {}

    lines = [
        f"Radiation Damage Analysis for {material_id}",
        "",
        f"- Structural integrity: {integrity}",
        f"- Confidence: {confidence}",
        f"- Total fluence: {analysis.get('total_fluence_n_cm2')} n/cm²",
        f"- DPA: {analysis.get('dpa')}",
        f"- DBTT shift: {analysis.get('dbtt_shift_c')} C",
        f"- Void swelling: {analysis.get('void_swelling_percent')} %",
        f"- Helium concentration: {analysis.get('helium_concentration_appm')} appm",
        f"- Hydrogen concentration: {analysis.get('hydrogen_concentration_appm')} appm",
        f"- Remaining service life: {analysis.get('remaining_service_life_years')} years",
        "",
        "Fluence spectrum:",
        f"- Thermal: {fluence_spectrum.get('thermal')}",
        f"- Epithermal: {fluence_spectrum.get('epithermal')}",
        f"- Fast: {fluence_spectrum.get('fast')}",
        "",
        "Surveillance capsule data:",
        f"- Capsules remaining: {surveillance.get('capsules_remaining')}",
        f"- Next withdrawal: {surveillance.get('next_withdrawal_date')}",
        "",
        "Regulatory compliance:",
        f"- Regulatory DBTT limit: {regulatory.get('regulatory_limit_dbtt_c')} C",
        f"- Margin to limit: {regulatory.get('margin_to_limit_c')} C",
        f"- Status: {regulatory.get('status')}",
    ]

    if mechanisms:
        lines.extend(["", "Active damage mechanisms:"])
        for m in mechanisms:
            lines.append(f"- {m}")

    if recommendations:
        lines.extend(["", "Recommendations:"])
        for item in recommendations:
            lines.append(f"- {item}")

    return "\n".join(lines)


class RadiationDamageAgent(PrometheusAgent):
    """Agent for radiation damage analysis."""

    def _merge_resolved_inputs(self, resolved: Dict[str, Any], params: Dict[str, Any], context: RequestContext) -> Dict[str, Any]:
        merged = dict(resolved or {})
        if params.get("material_id"):
            merged["material_id"] = params["material_id"]

        operating_context = params.get("context", {})
        if isinstance(operating_context, dict):
            for key in ("temperature_c", "pressure_mpa", "operating_hours"):
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
        Perform radiation damage analysis using Claude for expert assessment.

        Uses the Anthropic API to generate expert-level radiation damage analysis
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
                        description="Canonical material identifier for the radiation damage analysis.",
                        user_prompt="Which material should I analyze for radiation damage?",
                        type="string",
                        resolvable_from_context=True,
                    )
                ],
                hint="I need the target material before I can run the radiation damage analysis.",
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
                "analysis_type": "radiation_damage",
                "error": "ANTHROPIC_API_KEY not configured",
            }

        # Send status update
        await self.send_status_update(context=context, event_queue=event_queue)

        operating_context = {
            "temperature_c": resolved.get("temperature_c"),
            "pressure_mpa": resolved.get("pressure_mpa"),
            "operating_hours": resolved.get("operating_hours"),
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

            message = _build_radiation_summary(material_id, analysis)
            report = _build_radiation_report(material_id, analysis)

            await self.send_json_artifact(
                context=context,
                event_queue=event_queue,
                payload=analysis,
                name=f"{material_id.lower()}_radiation_damage",
                description=f"Radiation damage analysis result for {material_id}.",
                json_type=RADIATION_DAMAGE_JSON_TYPE,
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
                "analysis_type": "radiation_damage",
                "error": f"Analysis failed: {str(e)}",
            }


if __name__ == "__main__":
    agent = RadiationDamageAgent(agent_name="Radiation Damage Analysis Agent")
    agent.run()
