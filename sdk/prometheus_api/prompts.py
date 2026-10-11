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

"""Prompt-loading utilities for Prometheus agents."""

from __future__ import annotations

from os import PathLike
from pathlib import Path

Pathish = str | PathLike[str]


def _default_prompts_dir() -> Path:
    """Return the conventional prompts directory next to the running entrypoint."""
    import __main__

    main_file = getattr(__main__, "__file__", None)
    if main_file:
        return Path(main_file).resolve().parent / "prompts"
    return Path.cwd() / "prompts"


def _resolve_prompt_path(name: Pathish, prompts_dir: Pathish | None) -> Path:
    prompt_name = Path(name)
    if prompt_name.is_absolute():
        raise ValueError("Prompt name must be a relative path")

    base_dir = Path(prompts_dir).expanduser() if prompts_dir is not None else _default_prompts_dir()
    base_dir = base_dir.resolve()
    prompt_path = (base_dir / prompt_name).resolve()

    try:
        prompt_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(f"Prompt path escapes prompt directory: {name}") from exc

    return prompt_path


def load_prompt(
    name: Pathish,
    *,
    prompts_dir: Pathish | None = None,
    encoding: str = "utf-8",
    strip: bool = True,
) -> str:
    """Load a prompt template from a prompts directory.

    By default, prompts are loaded from ``prompts/`` next to the running
    agent entrypoint. Pass ``prompts_dir`` to use another directory.
    """
    prompt_path = _resolve_prompt_path(name, prompts_dir)
    text = prompt_path.read_text(encoding=encoding)
    return text.strip() if strip else text


__all__ = ["load_prompt"]
