"""
Data Agent - Specialist for nuclear material data retrieval
Implements A2A protocol using prometheus_api with Bearer token authentication
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from anthropic import Anthropic
from prometheus_api.agent import PrometheusAgent
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")

# Simulated material database
MATERIAL_DATABASE = {
    "SS316": {
        "material_id": "SS316",
        "name": "Stainless Steel 316 - Primary Coolant Piping",
        "specification": "ASTM A312 Type 316",
        "composition": {
            "C": 0.08, "Cr": 17.0, "Ni": 12.0, "Mo": 2.5,
            "Mn": 2.0, "Si": 1.0, "P": 0.045, "S": 0.030, "Fe": "balance"
        },
        "mechanical_properties": {
            "yield_strength_mpa": 290,
            "tensile_strength_mpa": 580,
            "elongation_percent": 40,
            "hardness_hb": 217
        },
        "thermal_properties": {
            "conductivity_w_mk": 16.3,
            "expansion_coeff_per_k": 15.9e-6,
            "specific_heat_j_kgk": 500
        },
        "installation_date": "2018-06-15",
        "design_life_years": 40,
        "location": "Primary coolant loop piping",
        "operating_environment": {
            "temperature_range_c": [280, 343],
            "pressure_mpa": 15.5,
            "coolant": "Light water (H2O) with boric acid",
            "radiation_field": "Moderate neutron flux"
        }
    },
    "SS316L": {
        "material_id": "SS316L",
        "name": "Stainless Steel 316L - Heat Exchanger",
        "specification": "ASTM A240 Type 316L",
        "composition": {
            "C": 0.03, "Cr": 17.0, "Ni": 12.0, "Mo": 2.5,
            "Mn": 2.0, "Si": 1.0, "P": 0.045, "S": 0.030, "Fe": "balance"
        },
        "mechanical_properties": {
            "yield_strength_mpa": 270,
            "tensile_strength_mpa": 560,
            "elongation_percent": 45,
            "hardness_hb": 201
        },
        "thermal_properties": {
            "conductivity_w_mk": 16.3,
            "expansion_coeff_per_k": 15.9e-6,
            "specific_heat_j_kgk": 500
        },
        "installation_date": "2015-03-20",
        "design_life_years": 40,
        "location": "Heat exchanger tubes",
        "operating_environment": {
            "temperature_range_c": [200, 320],
            "pressure_mpa": 10.5,
            "coolant": "Demineralized water",
            "radiation_field": "Low"
        }
    },
    "SS304": {
        "material_id": "SS304",
        "name": "Stainless Steel 304 - Structural Components",
        "specification": "ASTM A240 Type 304",
        "composition": {
            "C": 0.08, "Cr": 19.0, "Ni": 9.0,
            "Mn": 2.0, "Si": 1.0, "P": 0.045, "S": 0.030, "Fe": "balance"
        },
        "mechanical_properties": {
            "yield_strength_mpa": 215,
            "tensile_strength_mpa": 505,
            "elongation_percent": 40,
            "hardness_hb": 201
        },
        "thermal_properties": {
            "conductivity_w_mk": 16.2,
            "expansion_coeff_per_k": 17.3e-6,
            "specific_heat_j_kgk": 500
        },
        "installation_date": "2012-09-10",
        "design_life_years": 40,
        "location": "Containment structure internals",
        "operating_environment": {
            "temperature_range_c": [20, 250],
            "pressure_mpa": 0.4,
            "coolant": "Air/steam atmosphere",
            "radiation_field": "Very low"
        }
    },
    "SS347": {
        "material_id": "SS347",
        "name": "Stainless Steel 347 - High Temperature Piping",
        "specification": "ASTM A312 Type 347",
        "composition": {
            "C": 0.08, "Cr": 18.0, "Ni": 11.0, "Nb": 0.8,
            "Mn": 2.0, "Si": 1.0, "P": 0.045, "S": 0.030, "Fe": "balance"
        },
        "mechanical_properties": {
            "yield_strength_mpa": 240,
            "tensile_strength_mpa": 550,
            "elongation_percent": 40,
            "hardness_hb": 201
        },
        "thermal_properties": {
            "conductivity_w_mk": 16.3,
            "expansion_coeff_per_k": 17.8e-6,
            "specific_heat_j_kgk": 500
        },
        "installation_date": "2016-11-05",
        "design_life_years": 40,
        "location": "Steam generator feedwater piping",
        "operating_environment": {
            "temperature_range_c": [250, 400],
            "pressure_mpa": 18.0,
            "coolant": "High-temperature water/steam",
            "radiation_field": "Low"
        }
    }
}


class MaterialDataAgent(PrometheusAgent):
    """Agent for material data retrieval."""

    async def _execute(
        self,
        params: Dict[str, Any],
        context: RequestContext,
        event_queue: EventQueue,
    ) -> Dict[str, Any]:
        """
        Retrieve material data and provide intelligent interpretation using Claude.

        Supports two modes:
        - list_materials: No material_id required, returns list of all materials
        - get_material_data: Requires material_id, returns detailed data

        Returns comprehensive material property data with AI-generated insights
        about the material's characteristics and operational considerations.
        """
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Parsing material data request.",
        )

        material_id = params.get("material_id")

        # If no material_id provided, list all available materials
        if not material_id:
            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Listing all available materials.",
            )
            materials = [
                {
                    "material_id": mat_id,
                    "name": data["name"],
                    "specification": data["specification"],
                    "max_temp_c": data["operating_environment"]["temperature_range_c"][1],
                    "applications": data["location"],
                }
                for mat_id, data in MATERIAL_DATABASE.items()
            ]
            return {
                "query_type": "list_materials",
                "materials": materials,
                "count": len(materials),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message=f"Looking up data for material {material_id}.",
        )

        if material_id not in MATERIAL_DATABASE:
            return {
                "error": f"Material {material_id} not found",
                "available_materials": list(MATERIAL_DATABASE.keys()),
            }

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Building material profile response.",
        )

        material = MATERIAL_DATABASE[material_id]

        # Build base response with historical data
        base_data = {
            "material_id": material_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_type": "material_data",
            "material_data": material,
            "inspection_history": {
                "last_inspection": "2023-04-10",
                "inspection_type": "Ultrasonic Testing (UT)",
                "result": "acceptable",
                "inspections": [
                    {"date": "2020-04-15", "type": "UT", "result": "acceptable", "defects_found": 0},
                    {"date": "2021-10-20", "type": "VT", "result": "acceptable", "defects_found": 0},
                    {"date": "2023-04-10", "type": "UT", "result": "acceptable", "defects_found": 0},
                ],
            },
            "operational_history": {
                "operating_hours": 125000,
                "thermal_cycles": 1250,
                "repairs": [],
                "modifications": [],
            },
            "regulatory_info": {
                "applicable_codes": [
                    "ASME Section III",
                    "ASME Section XI",
                    "10 CFR 50.55a",
                    "10 CFR 50.61",
                ],
                "limits": {
                    "max_fluence_n_cm2": 1.0e20,
                    "max_dbtt_shift_c": 55.6,
                    "min_upper_shelf_energy_j": 68,
                    "max_flaw_size_mm": 6.35,
                    "max_creep_strain_percent": 1.0,
                },
                "inspection_requirements": {
                    "volumetric_interval_years": 10,
                    "surface_interval_years": 10,
                    "visual_interval_years": 3,
                },
            },
        }

        # Use Claude to provide intelligent interpretation
        if ANTHROPIC_API_KEY:
            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="Generating expert interpretation.",
            )
            try:
                prompt = f"""You are a nuclear materials engineer. Analyze this material data and provide expert insights.

Material ID: {material_id}
Data: {json.dumps(material, indent=2)}

Provide a brief expert commentary as a JSON object:
{{
    "material_assessment": "<brief assessment of material suitability>",
    "key_strengths": [<list of 2-3 key advantages>],
    "potential_concerns": [<list of 2-3 potential concerns>],
    "recommended_monitoring": [<list of 2-3 specific monitoring recommendations>],
    "compatibility_notes": "<brief note on compatibility with reactor environment>"
}}

Be concise and focus on actionable insights."""

                client = Anthropic(api_key=ANTHROPIC_API_KEY)
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=MODEL_NAME,
                    max_tokens=1024,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )

                response_text = response.content[0].text
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                interpretation = json.loads(response_text)
                base_data["ai_interpretation"] = interpretation
                base_data["model_used"] = MODEL_NAME
                await self.send_status_update(
                    context=context,
                    event_queue=event_queue,
                    message="Expert interpretation complete.",
                )

            except Exception as e:
                base_data["ai_interpretation"] = {"error": f"Interpretation failed: {str(e)}"}
                await self.send_status_update(
                    context=context,
                    event_queue=event_queue,
                    message="Interpretation failed; returning base material data.",
                )
        else:
            await self.send_status_update(
                context=context,
                event_queue=event_queue,
                message="No model API key configured; returning base material data.",
            )

        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Finalizing material data response.",
        )

        return base_data


if __name__ == "__main__":
    agent = MaterialDataAgent(agent_name="Material Data Agent")
    agent.run()
