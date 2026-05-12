"""IFC 3D building model visualization plugin."""

import tempfile
from pathlib import Path
from typing import Any, Optional

import httpx

MIMETYPES = ["model/ifc", "application/ifc"]
UPLOAD_EXTENSIONS = [".ifc"]
COMPONENT_NAME = "IFCViewer"
GENERIC_UPLOAD_MIMETYPES = {"", "application/octet-stream", "binary/octet-stream"}


def _resolve_path(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


def _normalize_mime_type(mime_type: str | None) -> str:
    return (mime_type or "").split(";", 1)[0].strip().lower()


async def detect_upload_mime(file_path: Path, mime_type: str | None = None) -> str | None:
    """Identify IFC STEP physical files from their contents when MIME is generic."""
    normalized = _normalize_mime_type(mime_type)
    if normalized in MIMETYPES:
        return normalized
    if normalized not in GENERIC_UPLOAD_MIMETYPES:
        return None

    try:
        with file_path.open("rb") as stream:
            sample = stream.read(65536)
    except Exception:
        return None

    text = sample.decode("latin-1", errors="ignore").upper()
    if "ISO-10303-21" in text and "FILE_SCHEMA" in text and "IFC" in text:
        return MIMETYPES[0]
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
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(uri)
            response.raise_for_status()
        with tempfile.TemporaryDirectory(prefix="ifc-artifact-") as tmp_dir:
            tmp_path = Path(tmp_dir) / Path(name).name
            tmp_path.write_bytes(response.content)
            from components.ifc_integration import process_ifc_upload
            dataset = await process_ifc_upload(tmp_path)
        return dataset.to_chainlit_element()

    return None


async def process_upload(file_path: Path) -> tuple[str, list]:
    from components.ifc_integration import process_ifc_upload, format_file_size
    dataset = await process_ifc_upload(file_path)
    desc = f"**IFC model loaded:** {file_path.name} ({format_file_size(dataset.file_size)})"
    return desc, [dataset.to_chainlit_element()]
