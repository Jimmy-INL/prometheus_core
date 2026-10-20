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

"""Unit tests for the agent-provided workflow source health check."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

CLIENT_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_AGENT_DIR))

from workflow_library import health

SOURCE_URL = "http://provider-agent:8000"


def _workflow() -> SimpleNamespace:
    """A workflow whose metadata points at the provider agent."""
    metadata = {"source_agent_id": "provider-agent", "source_agent_url": SOURCE_URL}
    return SimpleNamespace(definition=SimpleNamespace(metadata=metadata))


def _check(monkeypatch, routes: dict[str, int]) -> tuple[str | None, list[str]]:
    """Run the health check against stub ``routes`` (path -> status); return its result and the paths hit."""
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        return httpx.Response(routes.get(request.url.path, 404), json={"ok": True})

    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(health.httpx, "AsyncClient", client)
    return asyncio.run(health.verify_workflow_source_health(_workflow())), hits


def test_probes_healthz(monkeypatch) -> None:
    """A healthy agent is checked on /healthz alone."""
    result, hits = _check(monkeypatch, {"/healthz": 200})
    assert result is None
    assert hits == ["/healthz"]


def test_reports_unhealthy(monkeypatch) -> None:
    """An error on /healthz is reported."""
    result, hits = _check(monkeypatch, {"/healthz": 503})
    assert result is not None and "GET http://provider-agent:8000/healthz returned 503" in result
    assert hits == ["/healthz"]


def test_does_not_fall_back_to_health(monkeypatch) -> None:
    """An agent serving only the removed /health route is reported unhealthy."""
    result, hits = _check(monkeypatch, {"/health": 200})
    assert result is not None and "GET http://provider-agent:8000/healthz returned 404" in result
    assert hits == ["/healthz"]
