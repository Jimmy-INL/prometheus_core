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

"""Tests for the chat-history title generator (`_maybe_generate_title`).

Best-effort by design: a title failure must never raise into the caller
(``chat_flow.chat``), and once a title is set it must never be regenerated.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from orchestrator import chat_flow, runtime


class _FakeTitleLLM:
    """Async-context-manager stand-in for AsyncLLMClient, matching the
    ``async with runtime.create_llm() as llm: await llm.small(...)`` shape."""

    def __init__(self, text: str = "Corrosion rate of SS316", raise_error: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self._text = text
        self._raise = raise_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def small(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        if self._raise:
            raise RuntimeError("boom")
        return SimpleNamespace(text=self._text)


def test_maybe_generate_title_sets_title_from_small_llm(monkeypatch) -> None:
    fake_llm = _FakeTitleLLM(text="Corrosion rate of SS316")
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    state = {"title": None, "user_query": "What is the corrosion rate of SS316 in seawater?"}
    asyncio.run(chat_flow._maybe_generate_title(state, "conv-1"))

    assert state["title"] == "Corrosion rate of SS316"
    assert len(fake_llm.calls) == 1


def test_maybe_generate_title_skips_when_already_set(monkeypatch) -> None:
    """Runs once per conversation: a later turn must not call the LLM again."""
    fake_llm = _FakeTitleLLM()
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    state = {"title": "Existing title", "user_query": "a follow-up question"}
    asyncio.run(chat_flow._maybe_generate_title(state, "conv-1"))

    assert state["title"] == "Existing title"
    assert fake_llm.calls == []


def test_maybe_generate_title_skips_when_no_query() -> None:
    state = {"title": None, "user_query": ""}
    asyncio.run(chat_flow._maybe_generate_title(state, "conv-1"))

    assert state.get("title") is None


def test_maybe_generate_title_is_best_effort_on_llm_failure(monkeypatch) -> None:
    fake_llm = _FakeTitleLLM(raise_error=True)
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    state = {"title": None, "user_query": "hello"}
    # Must not raise -- a title failure can never fail the turn.
    asyncio.run(chat_flow._maybe_generate_title(state, "conv-1"))

    assert state.get("title") is None


def test_maybe_generate_title_truncates_long_output(monkeypatch) -> None:
    long_text = "x" * 200
    fake_llm = _FakeTitleLLM(text=long_text)
    monkeypatch.setattr(runtime, "create_llm", lambda: fake_llm)

    state = {"title": None, "user_query": "hello"}
    asyncio.run(chat_flow._maybe_generate_title(state, "conv-1"))

    assert state["title"] == long_text[: chat_flow._TITLE_MAX_CHARS]
