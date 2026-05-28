"""Shared upload contracts for visualization plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GENERIC_UPLOAD_MIMETYPES = {"", "application/octet-stream", "binary/octet-stream"}


def normalize_mime_type(mime_type: str | None) -> str:
    """Normalize a MIME value for registry lookup."""
    return (mime_type or "").split(";", 1)[0].strip().lower()


@dataclass(frozen=True)
class UploadContext:
    file_path: Path
    display_name: str
    mime_type: str
    size_bytes: int

    @property
    def suffix(self) -> str:
        return (Path(self.display_name).suffix or self.file_path.suffix).lower()


@dataclass(frozen=True)
class UploadMatch:
    mime_type: str
    confidence: int = 50
    reason: str = ""
    plugin: Any | None = None


@dataclass
class UploadRenderResult:
    description: str
    elements: list[Any] = field(default_factory=list)
    add_download: bool = True
