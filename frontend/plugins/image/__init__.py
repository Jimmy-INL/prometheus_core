"""Raster image visualization plugin (PNG, JPEG, GIF, WebP).

Uses cl.Image for inline display. Content is always resolved server-side
(local path or httpx fetch) to avoid browser CORS issues.
"""

import tempfile
from pathlib import Path
from typing import Any, Optional

import chainlit as cl
import httpx

MIMETYPES = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
TAGS = ["png", "jpeg", "jpg", "gif", "webp", "image"]
EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
UPLOAD_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
COMPONENT_NAME = None  # uses cl.Image, not a CustomElement


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


async def process_upload(file_path: Path) -> tuple[str, list]:
    element = cl.Image(name=file_path.name, path=str(file_path), display="inline")
    return f"**Image loaded:** {file_path.name}", [element]
