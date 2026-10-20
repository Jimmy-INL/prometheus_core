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

"""Health checks for agent-provided workflow templates."""
from __future__ import annotations

from typing import Any, Optional

import httpx


def _metadata_value(workflow: Any, key: str) -> Optional[str]:
    definition = getattr(workflow, "definition", None)
    metadata = getattr(definition, "metadata", None)
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        value = metadata.get(key)
    else:
        value = getattr(metadata, key, None)
    text = str(value or "").strip()
    return text or None


def workflow_source_agent_id(workflow: Any) -> Optional[str]:
    """Return the provider agent ID for an agent-provided workflow."""
    return _metadata_value(workflow, "source_agent_id")


def workflow_source_agent_url(workflow: Any) -> Optional[str]:
    """Return the provider agent direct URL for an agent-provided workflow."""
    return _metadata_value(workflow, "source_agent_url")


async def verify_workflow_source_health(workflow: Any, *, timeout_seconds: float = 3.0) -> Optional[str]:
    """Return an error message when an agent-provided workflow's source is unhealthy.

    Local platform workflows have no `source_agent_*` metadata and do not require
    this guard. Agent-provided workflows must carry a direct provider URL so the
    client-agent can confirm that the contributing agent has not been disconnected
    or scaled down before the workflow starts.
    """
    source_agent_id = workflow_source_agent_id(workflow)
    source_agent_url = workflow_source_agent_url(workflow)
    if not source_agent_id and not source_agent_url:
        return None

    label = source_agent_id or source_agent_url or "unknown"
    if not source_agent_url:
        return f"Workflow provider agent '{label}' has no health-check URL."

    health_url = f"{source_agent_url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(health_url)
    except httpx.RequestError as exc:
        return f"Workflow provider agent '{label}' is unavailable: {exc}"

    if response.status_code < 200 or response.status_code >= 300:
        return (
            f"Workflow provider agent '{label}' is unhealthy: "
            f"GET {health_url} returned {response.status_code}."
        )
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("ok") is False:
        return f"Workflow provider agent '{label}' is unhealthy: health response ok=false."

    return None
