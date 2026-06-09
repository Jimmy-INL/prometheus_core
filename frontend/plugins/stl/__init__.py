"""STL mesh visualization plugin.

Renders STL files through the shared VTK→VTP→``ExodusViewer`` pipeline (see
``components/stl_integration.py``). Handles both user uploads and agent-emitted
STL artifacts. No JSX of its own — it reuses ``ExodusViewer``.
"""

from pathlib import Path
from typing import Any, Optional

from plugins import (
    GENERIC_UPLOAD_MIMETYPES,
    UploadContext,
    UploadMatch,
    UploadRenderResult,
    normalize_mime_type,
)

MIMETYPES = [
    "model/stl",
    "application/sla",
    "application/vnd.ms-pki.stl",
    "model/x.stl-binary",
    "model/x.stl-ascii",
]
UPLOAD_EXTENSIONS = [".stl"]
COMPONENT_NAME = "ExodusViewer"  # reuse the shared VTK viewer


def _resolve_path(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


async def inspect_upload(context: UploadContext) -> UploadMatch | None:
    """Identify STL uploads from MIME/extension, confirmed by an actual VTK read.

    STL has no reliable magic number (ASCII begins with ``solid``; binary has an
    arbitrary 80-byte header), so we confirm candidates by reading them and
    checking that triangles came back — the same "inspect by reading" approach the
    Exodus plugin uses.
    """
    normalized = normalize_mime_type(context.mime_type)
    if normalized in MIMETYPES:
        return UploadMatch(mime_type=normalized, confidence=90, reason="declared STL MIME")

    should_inspect = normalized in GENERIC_UPLOAD_MIMETYPES or context.suffix in UPLOAD_EXTENSIONS
    if not should_inspect:
        return None

    try:
        from components.stl_integration import inspect_stl_file_async

        await inspect_stl_file_async(context.file_path)
    except Exception:
        return None

    confidence = 70 + (15 if context.suffix in UPLOAD_EXTENSIONS else 0)
    return UploadMatch(
        mime_type=MIMETYPES[0],
        confidence=min(confidence, 95),
        reason="STL content inspection",
    )


async def render_artifact(artifact: dict) -> Optional[Any]:
    """Render an agent-emitted STL artifact (a ``model/stl`` file reference)."""
    file_path = _resolve_path(artifact.get("uri") or "")
    if not file_path or not file_path.exists():
        return None
    from components.stl_integration import process_stl_upload

    dataset = await process_stl_upload(file_path)
    return dataset.to_chainlit_element()


async def process_upload(context: UploadContext) -> UploadRenderResult:
    """Convert and render a user-uploaded STL file."""
    from components.stl_integration import process_stl_upload

    dataset = await process_stl_upload(context.file_path)
    meta = dataset.metadata or {}
    lines = [f"**STL mesh loaded:** `{context.display_name}`"]
    if meta.get("num_nodes"):
        lines.append(f"- Vertices: {meta['num_nodes']:,}")
    if meta.get("num_elements"):
        lines.append(f"- Triangles: {meta['num_elements']:,}")
    return UploadRenderResult("\n".join(lines), [dataset.to_chainlit_element()])
