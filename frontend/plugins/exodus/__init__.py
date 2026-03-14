"""Exodus II mesh visualization plugin."""

from pathlib import Path
from typing import Any, Optional

import chainlit as cl

MIMETYPES = ["application/x-exodus", "application/exodus"]
TAGS = ["exodus", "vtk"]
EXTENSIONS = [".exo", ".e"]
UPLOAD_EXTENSIONS = [".exo", ".e"]
COMPONENT_NAME = "ExodusViewer"


def _resolve_path(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


async def render_artifact(artifact: dict) -> Optional[Any]:
    file_path = _resolve_path(artifact.get("uri") or "")
    if not file_path or not file_path.exists():
        return None
    from components.exodus_integration import process_exodus_upload
    dataset = await process_exodus_upload(file_path)
    return dataset.to_chainlit_element()


async def process_upload(file_path: Path) -> tuple[str, list]:
    from components.exodus_integration import process_exodus_upload
    dataset = await process_exodus_upload(file_path)
    meta = dataset.metadata or {}
    lines = [f"**Exodus mesh loaded:** `{file_path.name}`"]
    if meta.get("num_timesteps"):
        lines.append(f"- Timesteps: {meta['num_timesteps']}")
    if meta.get("num_nodes"):
        lines.append(f"- Nodes: {meta['num_nodes']:,}")
    if meta.get("num_elements"):
        lines.append(f"- Elements: {meta['num_elements']:,}")
    all_vars = meta.get("nodal_variables", []) + meta.get("element_variables", [])
    if all_vars:
        lines.append(
            f"- Variables: {', '.join(all_vars[:5])}{'...' if len(all_vars) > 5 else ''}"
        )
    return "\n".join(lines), [dataset.to_chainlit_element()]
