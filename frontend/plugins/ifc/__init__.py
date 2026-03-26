"""IFC 3D building model visualization plugin."""

import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

import chainlit as cl
import httpx

MIMETYPES = ["model/ifc", "application/ifc"]
UPLOAD_EXTENSIONS = [".ifc"]
COMPONENT_NAME = "IFCViewer"


def _resolve_path(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


async def render_artifact(artifact: dict) -> Optional[Any]:
    uri = artifact.get("uri") or ""
    name = artifact.get("name", "model.ifc")

    file_path = _resolve_path(uri)
    if file_path and file_path.exists():
        from components.ifc_integration import process_ifc_upload
        dataset = await process_ifc_upload(file_path)
        return dataset.to_chainlit_element()

    if uri.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(uri)
                response.raise_for_status()
            tmp_dir = Path(tempfile.mkdtemp(prefix="ifc-artifact-"))
            tmp_path = tmp_dir / Path(name).name
            tmp_path.write_bytes(response.content)
            from components.ifc_integration import process_ifc_upload
            dataset = await process_ifc_upload(tmp_path)
            return dataset.to_chainlit_element()
        except Exception:
            dataset_id = str(uuid.uuid4())[:8]
            return cl.CustomElement(
                name=COMPONENT_NAME,
                display="inline",
                props={"datasetId": dataset_id, "fileUrl": uri, "filename": name},
            )

    return None


async def process_upload(file_path: Path) -> tuple[str, list]:
    from components.ifc_integration import process_ifc_upload, format_file_size
    dataset = await process_ifc_upload(file_path)
    desc = f"**IFC model loaded:** {file_path.name} ({format_file_size(dataset.file_size)})"
    return desc, [dataset.to_chainlit_element()]
