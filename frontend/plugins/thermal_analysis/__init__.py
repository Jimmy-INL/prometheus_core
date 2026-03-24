"""Thermal analysis JSON visualization plugin."""

from typing import Any, Optional

JSON_TYPES = ["prometheus.thermal_analysis.result.v1"]
MIMETYPES: list[str] = []
UPLOAD_EXTENSIONS: list[str] = []
COMPONENT_NAME = "ThermalAnalysisViewer"


async def render_artifact(artifact: dict) -> Optional[Any]:
    import chainlit as cl

    data = artifact.get("json_body")
    if not isinstance(data, dict):
        return None

    return cl.CustomElement(
        name=COMPONENT_NAME,
        display="inline",
        props={
            "name": artifact.get("name") or "thermal_analysis",
            "description": artifact.get("description") or "",
            "analysis": data,
        },
    )
