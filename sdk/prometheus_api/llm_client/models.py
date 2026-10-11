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
