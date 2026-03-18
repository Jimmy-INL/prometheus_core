"""Mermaid diagram visualization plugin."""

from typing import Any, Optional

import chainlit as cl

MIMETYPES = ["text/x-mermaid", "application/vnd.mermaid"]
UPLOAD_EXTENSIONS = []
COMPONENT_NAME = "MermaidViewer"


async def render_artifact(artifact: dict) -> Optional[Any]:
    metadata = artifact.get("metadata") or {}
    diagram = (
        artifact.get("content")
        or metadata.get("content")
        or metadata.get("chart")
        or ""
    )
    if not diagram:
        return None
    return cl.CustomElement(
        name=COMPONENT_NAME,
        display="inline",
        props={"diagram": diagram, "title": artifact.get("name", "")},
    )
