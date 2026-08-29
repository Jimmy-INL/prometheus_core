"""Upload staging — MIME guessing, size enforcement, DeepLynx staging (decision D5).

Ports the *keep* half of ``frontend/components/message_handler.py``'s upload path:

- ``_guess_upload_mime`` (message_handler.py:62) — stable MIME resolution including
  the CAD ``.stp``/``.step`` → ``model/step`` mapping and the generic-MIME fallback.
- ``_capture_uploaded_file`` (message_handler.py:84) — size limit + ``stage_upload``,
  requiring an ``upload_id`` in the staging response.

Dropped (out of scope, task 06): plugin ``inspect_upload`` / ``process_upload`` and
local previews — those built Chainlit elements and are now a frontend concern. This
module keeps only: size limit, MIME guess, stage.
"""

from __future__ import annotations

import logging
import math
import mimetypes
from pathlib import Path
from typing import Optional

from app.a2a_client import A2AClient
from app.config import settings
from app.contract import UploadDescriptor

logger = logging.getLogger(__name__)

# Ported verbatim from message_handler.py / plugins.upload_contract. Re-declared here
# rather than imported so backend stays decoupled from the Chainlit ``plugins``
# package (task ground rule: port, don't couple).
GENERIC_UPLOAD_MIMETYPES = {"", "application/octet-stream", "binary/octet-stream"}

CAD_EXTENSION_MIMETYPES = {
    ".stp": "model/step",
    ".step": "model/step",
}

MAX_UPLOAD_BYTES = settings.max_upload_bytes
MAX_UPLOAD_MB = max(1, math.ceil(MAX_UPLOAD_BYTES / (1024 * 1024)))


class UploadTooLargeError(Exception):
    """Raised when an upload exceeds ``MAX_UPLOAD_BYTES`` (→ 413 in the router)."""

    def __init__(self, name: str, size_bytes: int) -> None:
        self.name = name
        self.size_bytes = size_bytes
        super().__init__(upload_limit_message(name))


class UploadStagingError(Exception):
    """Raised when staging fails or returns no ``upload_id`` (→ 502 in the router)."""


def upload_limit_message(name: str) -> str:
    """Human-readable limit message (ports ``_upload_limit_message``)."""
    return f"**{name}** exceeds the {MAX_UPLOAD_MB} MB upload limit and will not be stored."


def _normalize_mime_type(mime_type: Optional[str]) -> str:
    """Normalize a MIME value (ports ``plugins.normalize_mime_type``)."""
    return (mime_type or "").split(";", 1)[0].strip().lower()


def guess_upload_mime(filename: str, element_mime: Optional[str] = None) -> str:
    """Return a stable MIME type for an uploaded file, including CAD extensions.

    Ported verbatim from ``message_handler._guess_upload_mime``: a concrete
    client-provided MIME wins; otherwise fall back to the CAD extension map, then
    ``mimetypes.guess_type``, then ``application/octet-stream``.
    """
    mime = _normalize_mime_type(element_mime)
    if mime and mime not in GENERIC_UPLOAD_MIMETYPES:
        return mime

    suffix = Path(filename).suffix.lower()
    if suffix in CAD_EXTENSION_MIMETYPES:
        return CAD_EXTENSION_MIMETYPES[suffix]
    return mimetypes.guess_type(filename)[0] or mime or "application/octet-stream"


async def stage_upload(
    client: A2AClient,
    file_path: Path,
    *,
    name: str,
    conversation_id: str,
    element_mime: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> UploadDescriptor:
    """Enforce the size limit, guess the MIME, and stage one file to DeepLynx.

    Ports ``_capture_uploaded_file`` (message_handler.py:84) minus its Chainlit
    messaging: over-limit raises :class:`UploadTooLargeError`; a staging failure or
    a response missing ``upload_id`` raises :class:`UploadStagingError`. On success
    returns the wire :class:`UploadDescriptor` the frontend echoes back on the next
    ``POST /api/chat/messages``.
    """
    size = size_bytes if size_bytes is not None else file_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(name, size)

    mime = guess_upload_mime(name, element_mime)
    try:
        staged = await client.stage_upload(
            file_path,
            name=name,
            mime_type=mime,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("Could not stage %r for upload: %s", name, exc)
        raise UploadStagingError(f"Failed to stage {name!r} for upload: {exc}") from exc

    upload_id = staged.get("upload_id")
    if not upload_id:
        raise UploadStagingError("Upload staging response did not include upload_id")

    return UploadDescriptor(
        upload_id=str(upload_id),
        name=staged.get("name") or name,
        mime_type=staged.get("mime_type") or mime,
        size_bytes=int(staged.get("size_bytes", size)),
    )
