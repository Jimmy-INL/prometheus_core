"""SVG inline visualization plugin.

Content is always resolved server-side so the browser never makes a
cross-origin request. Resolution order:
  1. artifact.content        — inline SVG already provided
  2. metadata.local_path     — container file path (e.g. /app/shared/…)
  3. artifact.uri file://    — explicit file:// URI
  4. artifact.uri local path — bare path that exists on disk
  5. artifact.uri http(s)    — fetch server-side via httpx
"""

from pathlib import Path
from typing import Any, Optional

import chainlit as cl
import httpx

from plugins import UploadContext, UploadMatch, UploadRenderResult, normalize_mime_type

MIMETYPES = ["image/svg+xml"]
UPLOAD_EXTENSIONS = [".svg"]
COMPONENT_NAME = "SVGViewer"


def _read_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _resolve_local(uri: str) -> Optional[Path]:
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p
    return None


async def _fetch_http(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return None


async def _resolve_content(artifact: dict) -> Optional[str]:
    # 1. Inline content
    if artifact.get("content"):
        return artifact["content"]

    # 2. local_path in metadata (artifact-debug-agent stores this)
    local_path_str = (artifact.get("metadata") or {}).get("local_path", "")
    if local_path_str:
        p = Path(local_path_str)
        if p.exists():
            content = _read_file(p)
            if content:
                return content

    # 3 & 4. URI — local file
    uri = artifact.get("uri") or ""
    local_path = _resolve_local(uri)
    if local_path and local_path.exists():
        content = _read_file(local_path)
        if content:
            return content

    # 5. HTTP URI — fetch server-side to avoid browser CORS issues
    if uri.startswith("http"):
        return await _fetch_http(uri)

    return None


async def render_artifact(artifact: dict) -> Optional[Any]:
    name = artifact.get("name", "image.svg")
    content = await _resolve_content(artifact)
    if not content:
        return None
    return cl.CustomElement(
        name=COMPONENT_NAME,
        display="inline",
        props={"svgContent": content, "svgUrl": "", "name": name},
    )


async def inspect_upload(context: UploadContext) -> UploadMatch | None:
    mime = normalize_mime_type(context.mime_type)
    if mime in MIMETYPES:
        return UploadMatch(mime_type=mime, confidence=90, reason="declared SVG MIME")
    if context.suffix in UPLOAD_EXTENSIONS:
        return UploadMatch(mime_type=MIMETYPES[0], confidence=60, reason="SVG file extension")
    return None


async def process_upload(context: UploadContext) -> UploadRenderResult:
    content = _read_file(context.file_path) or ""
    element = cl.CustomElement(
        name=COMPONENT_NAME,
        display="inline",
        props={"svgContent": content, "svgUrl": "", "name": context.display_name},
    )
    return UploadRenderResult(f"**SVG loaded:** {context.display_name}", [element])
