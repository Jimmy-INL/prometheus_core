"""Response objects returned by LLM client methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatResponse:
    """Normalized chat-completion response."""

    text: str
    model_alias: str
    provider_model: str | None
    usage: dict[str, Any] | None
    raw: Any


@dataclass(frozen=True)
class EmbeddingResponse:
    """Normalized embedding response."""

    embeddings: list[list[float]]
    model_alias: str
    provider_model: str | None
    usage: dict[str, Any] | None
    raw: Any
