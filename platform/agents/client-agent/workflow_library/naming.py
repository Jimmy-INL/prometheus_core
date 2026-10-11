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

"""Workflow names used for LLM tools and slash-command aliases."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Optional


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def workflow_slug(value: str) -> str:
    """Return a lowercase command-safe slug for a workflow label."""
    slug = _SLUG_RE.sub("_", str(value or "").lower()).strip("_")
    return slug or "workflow"


def workflow_tool_name(workflow_id: str) -> str:
    """Return a stable Anthropic/OpenAI-compatible tool name for a workflow."""
    slug = workflow_slug(workflow_id)
    name = f"workflow_{slug}"
    if len(name) <= 64:
        return name

    digest = hashlib.sha1(str(workflow_id).encode("utf-8")).hexdigest()[:8]
    prefix_length = 64 - len("_") - len(digest)
    return f"{name[:prefix_length].rstrip('_')}_{digest}"


def workflow_command_aliases(workflow: Any) -> list[str]:
    """Return slash-command aliases for a compiled workflow."""
    definition = getattr(workflow, "definition", None)
    workflow_id = str(getattr(definition, "id", "") or "").strip()
    aliases: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        lowered = text.lower()
        if lowered not in aliases:
            aliases.append(lowered)
        slug = workflow_slug(text)
        if slug not in aliases:
            aliases.append(slug)

    add(workflow_id)
    if "." in workflow_id:
        add(workflow_id.rsplit(".", 1)[-1])
    add(getattr(definition, "name", None))
    ui = getattr(definition, "ui", None)
    add(getattr(ui, "display_name", None))
    return aliases


def find_workflow_by_command(command: str, workflows: Iterable[Any]) -> Optional[Any]:
    """Resolve `/command` text to a unique workflow, if one exists."""
    normalized = str(command or "").strip().lower().lstrip("/")
    if not normalized:
        return None

    candidates = list(workflows)

    for workflow in candidates:
        definition = getattr(workflow, "definition", None)
        if normalized == str(getattr(definition, "id", "") or "").strip().lower():
            return workflow

    for workflow in candidates:
        definition = getattr(workflow, "definition", None)
        if normalized == workflow_slug(str(getattr(definition, "id", "") or "")):
            return workflow

    matches = [
        workflow
        for workflow in candidates
        if normalized in workflow_command_aliases(workflow)
    ]
    return matches[0] if len(matches) == 1 else None
