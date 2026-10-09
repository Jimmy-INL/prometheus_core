"""Response objects returned by LLM client methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the import cycle open
    from .tools import ToolCall


@dataclass(frozen=True)
class ChatResponse:
    """Normalized chat-completion response.

    ``tool_calls`` and ``finish_reason`` are appended with defaults so existing
    positional and keyword construction keeps working. A pure tool-call turn has no
    message content, so ``text`` is empty and ``finish_reason`` plus ``tool_calls``
    carry the signal.
    """

    text: str
    model_alias: str
    provider_model: str | None
    usage: dict[str, Any] | None
    raw: Any
    tool_calls: tuple["ToolCall", ...] = ()
    finish_reason: str | None = None


@dataclass(frozen=True)
class EmbeddingResponse:
    """Normalized embedding response."""

    embeddings: list[list[float]]
    model_alias: str
    provider_model: str | None
    usage: dict[str, Any] | None
    raw: Any
