"""IFC 3D building model visualization plugin."""

import uuid
from pathlib import Path
from typing import Any, Optional

import chainlit as cl

MIMETYPES = ["model/ifc", "application/ifc"]
TAGS = ["ifc"]
EXTENSIONS = [".ifc"]
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
