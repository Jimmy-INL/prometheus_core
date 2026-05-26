"""Raster image visualization plugin (PNG, JPEG, GIF, WebP).

Uses cl.Image for inline display. Content is always resolved server-side
(local path or httpx fetch) to avoid browser CORS issues.
"""

import tempfile
from pathlib import Path
from typing import Any, Optional

import chainlit as cl
import httpx

from plugins import UploadContext, UploadMatch, UploadRenderResult, normalize_mime_type

MIMETYPES = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
UPLOAD_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
COMPONENT_NAME = None  # uses cl.Image, not a CustomElement
_EXTENSION_MIMETYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _resolve_local(uri: str, metadata: dict) -> Optional[Path]:
    # 1. local_path in metadata
    local = metadata.get("local_path", "")
    if local:
        p = Path(local)
        if p.exists():
            return p

    # 2. file:// URI
    if uri.startswith("file://"):
        p = Path(uri[7:])
        if p.exists():
            return p

    # 3. bare local path
    if uri and not uri.startswith("http"):
        p = Path(uri)
        if p.exists():
            return p

    return None


async def _fetch_to_tmp(url: str, suffix: str) -> Optional[Path]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        tmp = Path(tempfile.mkdtemp()) / f"image{suffix}"
        tmp.write_bytes(resp.content)
        return tmp
    except Exception:
        return None


async def render_artifact(artifact: dict) -> Optional[Any]:
    name = artifact.get("name", "image")
    uri = artifact.get("uri") or ""
    metadata = artifact.get("metadata") or {}
    suffix = Path(name).suffix or Path(uri).suffix or ".png"

    local_path = _resolve_local(uri, metadata)
    if not local_path and uri.startswith("http"):
        local_path = await _fetch_to_tmp(uri, suffix)

    if not local_path:
        return None

    return cl.Image(name=name, path=str(local_path), display="inline")


async def inspect_upload(context: UploadContext) -> UploadMatch | None:
    mime = normalize_mime_type(context.mime_type)
    if mime in MIMETYPES:
        return UploadMatch(mime_type=mime, confidence=90, reason="declared image MIME")
    if context.suffix in _EXTENSION_MIMETYPES:
        return UploadMatch(
            mime_type=_EXTENSION_MIMETYPES[context.suffix],
            confidence=60,
            reason="image file extension",
        )
    return None


async def process_upload(context: UploadContext) -> UploadRenderResult:
    element = cl.Image(name=context.display_name, path=str(context.file_path), display="inline")
    return UploadRenderResult(f"**Image loaded:** {context.display_name}", [element])
