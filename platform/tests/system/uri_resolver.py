# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""URI resolver for artifact references in the Prometheus frontend.

Resolves artifact URIs to local file paths on the frontend container so that
visualization plugins (SVG, image, Exodus, IFC, etc.) can read them without
making cross-origin requests.

Supported schemes:
  file://    - Already local; strip scheme and return the path.
  http(s):// - Download via httpx into the provided cache_dir.
  deeplynx://organizations/{org}/projects/{proj}/items/{item_id}
             - Download from DeepLynx using the file_id stored in the artifact
               metadata by PrometheusAgent.send_deeplynx_artifact.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _cache_path(cache_dir: Path, artifact_id: Optional[str], uri: str, filename: str) -> Path:
    """Derive a deterministic destination path to avoid repeat downloads."""
    key = artifact_id or hashlib.sha256(uri.encode()).hexdigest()[:16]
    return cache_dir / key / filename


async def resolve_to_local_path(
    uri: str,
    *,
    cache_dir: Path,
    artifact: Optional[Dict[str, Any]] = None,
    artifact_id: Optional[str] = None,
) -> Optional[Path]:
    """Resolve an artifact URI to a local file path on the frontend container.

    Returns None when the URI scheme is unsupported or the download fails.
    Callers should treat None as "no local file available" and fall through to
    text-based fallback rendering.
    """
    if not uri:
        return None

    artifact = artifact or {}
    name = artifact.get("name") or Path(uri).name or "artifact"

    if uri.startswith("file://"):
        return Path(uri[7:])

    if uri.startswith("http://") or uri.startswith("https://"):
        dest = _cache_path(cache_dir, artifact_id, uri, name)
        if dest.exists():
            logger.debug("URI cache hit: %s → %s", uri, dest)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(uri)
                resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.debug("Downloaded %s → %s", uri, dest)
            return dest
        except Exception as exc:
            logger.warning("Failed to download %s: %s", uri, exc)
            return None

    if uri.startswith("deeplynx://"):
        return await _resolve_deeplynx(
            uri,
            artifact=artifact,
            artifact_id=artifact_id,
            cache_dir=cache_dir,
            name=name,
        )

    return None


async def _resolve_deeplynx(
    uri: str,
    *,
    artifact: Dict[str, Any],
    artifact_id: Optional[str],
    cache_dir: Path,
    name: str,
) -> Optional[Path]:
    """Download a deeplynx:// artifact to a local cache path.

    Resolution strategy:
    1. Read deeplynx_file_id from artifact metadata (set by send_deeplynx_artifact).
    2. Fall back to parsing item_id from the URI, fetching the item, and reading
       properties["file_id"] — handles artifacts produced outside this agent.
    """
    dest = _cache_path(cache_dir, artifact_id, uri, name)
    if dest.exists():
        logger.debug("DeepLynx cache hit: %s → %s", uri, dest)
        return dest

    try:
        from prometheus_api.storage_client.async_client import AsyncStorageClient
        from prometheus_api.storage_client.connection import ConnectionConfig

        storage_config = ConnectionConfig.from_env()
    except (ImportError, ValueError) as exc:
        logger.warning("Cannot resolve deeplynx:// URI — credentials unavailable: %s", exc)
        return None

    metadata = artifact.get("metadata") or {}
    file_id = metadata.get("deeplynx_file_id")

    if not file_id:
        item_id = _parse_item_id(uri)
        if item_id is None:
            logger.warning("Cannot parse item_id from deeplynx:// URI: %s", uri)
            return None
        try:
            async with AsyncStorageClient(storage_config) as client:
                item = await client.items.get(item_id)
            file_id = (item.properties or {}).get("file_id")
        except Exception as exc:
            logger.warning("Failed to fetch DeepLynx item for %s: %s", uri, exc)
            return None

    if not file_id:
        logger.warning("No file_id found for deeplynx:// artifact: %s", uri)
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncStorageClient(storage_config) as client:
            await client.files.download(int(file_id), dest)
        logger.debug("Downloaded deeplynx:// %s → %s", uri, dest)
        return dest
    except Exception as exc:
        logger.warning("Failed to download deeplynx:// file %s (file_id=%s): %s", uri, file_id, exc)
        return None


def _parse_item_id(uri: str) -> Optional[int]:
    """Extract integer item_id from deeplynx://organizations/.../items/{id}."""
    parts = uri.rstrip("/").split("/")
    try:
        idx = parts.index("items")
        return int(parts[idx + 1])
    except (ValueError, IndexError):
        return None
