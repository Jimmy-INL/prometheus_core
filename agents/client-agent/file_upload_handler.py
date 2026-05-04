"""User-uploaded file ingestion: description inference and DeepLynx storage.

On each request that carries `uploaded_files`, the orchestrator calls
`infer_file_descriptions` (one LLM call) to produce a description for every
file, then `upload_files_to_deeplynx` to store them and register artifact
references.  The resulting artifact IDs are tracked as
`newly_uploaded_artifact_ids` in the conversation context for the current turn
so the planner can surface them with an ephemeral prefix and `resolve_artifact_inputs`
can auto-bind them to skill parameters.

See docs/dev-docs/file-uploads.md for the full workflow description.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

if TYPE_CHECKING:
    from prometheus_api.agent import ArtifactReference, EventQueue, RequestContext
    from prometheus_api.storage_client.connection import ConnectionConfig

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class UploadedFile(BaseModel):
    name: str
    mime_type: str
    size_bytes: int
    content_b64: str  # base64-encoded file content


# ---------------------------------------------------------------------------
# MIME → human-readable label
# ---------------------------------------------------------------------------

_EXACT_MIME_LABELS: Dict[str, str] = {
    "application/pdf": "PDF document",
    "application/json": "JSON data file",
    "text/csv": "CSV data file",
    "text/plain": "text file",
    "text/markdown": "Markdown document",
    "text/yaml": "YAML configuration file",
    "application/yaml": "YAML configuration file",
    "image/jpeg": "JPEG image",
    "image/png": "PNG image",
    "image/gif": "GIF image",
    "image/svg+xml": "SVG image",
    "image/webp": "WebP image",
    "image/tiff": "TIFF image",
    "application/zip": "ZIP archive",
    "application/gzip": "gzip archive",
    "application/x-tar": "tar archive",
    "application/x-hdf5": "HDF5 data file",
    "application/vnd.ms-excel": "Excel spreadsheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel spreadsheet",
}

_EXT_LABELS: Dict[str, str] = {
    ".e": "Exodus mesh file",
    ".exo": "Exodus mesh file",
    ".exodus": "Exodus mesh file",
    ".inp": "ABAQUS/Cubit input file",
    ".i": "MOOSE input file",
    ".yaml": "YAML configuration file",
    ".yml": "YAML configuration file",
    ".json": "JSON data file",
    ".csv": "CSV data file",
    ".txt": "text file",
    ".md": "Markdown document",
    ".pdf": "PDF document",
    ".h5": "HDF5 data file",
    ".hdf5": "HDF5 data file",
    ".nc": "NetCDF data file",
    ".vtu": "VTK unstructured grid file",
    ".vtp": "VTK polydata file",
    ".vtk": "VTK data file",
    ".stl": "STL geometry file",
    ".obj": "OBJ geometry file",
    ".step": "STEP CAD file",
    ".stp": "STEP CAD file",
    ".ifc": "IFC building model file",
    ".png": "PNG image",
    ".jpg": "JPEG image",
    ".jpeg": "JPEG image",
    ".svg": "SVG image",
    ".tif": "TIFF image",
    ".tiff": "TIFF image",
}


def mime_type_label(mime_type: str, filename: str = "") -> str:
    """Return a human-readable file type label from a MIME type and optional filename."""
    mime = (mime_type or "").lower().strip()

    if mime in _EXACT_MIME_LABELS:
        return _EXACT_MIME_LABELS[mime]

    ext = Path(filename).suffix.lower() if filename else ""
    if ext in _EXT_LABELS:
        return _EXT_LABELS[ext]

    if mime.startswith("image/"):
        return "image file"
    if mime.startswith("video/"):
        return "video file"
    if mime.startswith("audio/"):
        return "audio file"
    if mime.startswith("text/"):
        return "text file"
    if mime.startswith("application/"):
        subtype = mime.split("/", 1)[1].lstrip("x-").replace("-", " ").replace("_", " ")
        if subtype:
            return f"{subtype} file"

    return "file"


# ---------------------------------------------------------------------------
# Description inference
# ---------------------------------------------------------------------------

async def infer_file_descriptions(
    query: str,
    files: List[UploadedFile],
    llm: Any,
) -> Dict[str, str]:
    """Return {filename: description} for every uploaded file.

    The LLM is instructed to always produce a non-empty description.  When
    the query provides rich context it is used; otherwise the description is
    synthesised from the filename and MIME type alone.
    """
    file_list = "\n".join(
        f"- {f.name} ({mime_type_label(f.mime_type, f.name)}, {f.size_bytes:,} bytes)"
        for f in files
    )
    prompt = (
        "The user uploaded the following file(s) together with a query.\n\n"
        f"Files:\n{file_list}\n\n"
        f"User query: {query!r}\n\n"
        "For each file, write one concise sentence describing what it likely contains "
        "and why it was uploaded.  Use the query for context when it is informative; "
        "otherwise synthesise a description from the filename and file type alone "
        "(e.g. \"MOOSE Exodus mesh file for reactor core geometry.\").\n"
        "Always produce a non-empty string — never output null.\n\n"
        "Respond ONLY with a JSON object mapping each exact filename to its description:\n"
        '{"filename1": "description", "filename2": "description", ...}'
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    text = response.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            out: Dict[str, str] = {}
            for f in files:
                desc = result.get(f.name)
                out[f.name] = str(desc).strip() if desc else _fallback_description(f)
            return out
    except Exception:
        pass
    # If parsing fails fall back for all files
    return {f.name: _fallback_description(f) for f in files}


def _fallback_description(f: UploadedFile) -> str:
    label = mime_type_label(f.mime_type, f.name)
    return f"User-uploaded {label}: {f.name}"


# ---------------------------------------------------------------------------
# DeepLynx upload
# ---------------------------------------------------------------------------

async def upload_files_to_deeplynx(
    agent: Any,
    files: List[UploadedFile],
    descriptions: Dict[str, str],
    context: "RequestContext",
    event_queue: "EventQueue",
    storage_config: "ConnectionConfig",
) -> List["ArtifactReference"]:
    """Decode each file, upload to DeepLynx, and return ArtifactReferences."""
    refs = []
    for f in files:
        description = descriptions.get(f.name) or _fallback_description(f)
        suffix = Path(f.name).suffix or ""
        tmp_path: Optional[str] = None
        try:
            content = base64.b64decode(f.content_b64, validate=True)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            ref = await agent.send_deeplynx_artifact(
                context=context,
                event_queue=event_queue,
                file_path=Path(tmp_path),
                name=f.name,
                description=description,
                storage_config=storage_config,
                mime_type=f.mime_type,
                tags=["user-upload"],
                metadata={"original_filename": f.name, "source": "user-upload"},
            )
            refs.append(ref)
        except Exception as exc:
            print(f"[WARN] Failed to upload {f.name!r} to DeepLynx: {exc}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    return refs
