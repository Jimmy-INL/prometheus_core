"""Exodus II mesh visualization plugin."""

from pathlib import Path
from typing import Any, Optional

from plugins import GENERIC_UPLOAD_MIMETYPES, normalize_mime_type as _normalize_mime_type

MIMETYPES = ["application/x-exodus", "application/exodus"]
UPLOAD_EXTENSIONS = [".exo", ".e"]
COMPONENT_NAME = "ExodusViewer"
_EXODUS_CONTAINER_SIGNATURES = (b"CDF\x01", b"CDF\x02", b"\x89HDF\r\n\x1a\n")


def _resolve_path(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


def _has_exodus_container_signature(file_path: Path) -> bool:
    try:
        with file_path.open("rb") as stream:
            header = stream.read(16)
    except Exception:
        return False
    return any(header.startswith(signature) for signature in _EXODUS_CONTAINER_SIGNATURES)


async def detect_upload_mime(file_path: Path, mime_type: str | None = None) -> str | None:
    """Identify Exodus uploads from file contents when the browser MIME is generic."""
    normalized = _normalize_mime_type(mime_type)
    if normalized in MIMETYPES:
        return normalized
    if normalized not in GENERIC_UPLOAD_MIMETYPES:
        return None
    if not _has_exodus_container_signature(file_path):
        return None

    try:
        from components.exodus_integration import inspect_exodus_file_async

        await inspect_exodus_file_async(file_path)
    except Exception:
        return None
    return MIMETYPES[0]


async def render_artifact(artifact: dict) -> Optional[Any]:
    file_path = _resolve_path(artifact.get("uri") or "")
    if not file_path or not file_path.exists():
        return None
    from components.exodus_integration import process_exodus_upload
    dataset = await process_exodus_upload(file_path)
    return dataset.to_chainlit_element()


async def process_upload(file_path: Path, display_name: str | None = None) -> tuple[str, list]:
    from components.exodus_integration import process_exodus_upload
    dataset = await process_exodus_upload(file_path)
    meta = dataset.metadata or {}
    name = display_name or file_path.name
    lines = [f"**Exodus mesh loaded:** `{name}`"]
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
