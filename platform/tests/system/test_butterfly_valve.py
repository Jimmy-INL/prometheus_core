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

"""Exercise the ordinary butterfly-valve user experience end to end."""

from __future__ import annotations

from pathlib import Path

import pytest

from system.prometheus import (
    expect_parameter_request,
    expect_similar,
    prompt,
    start_chat,
    submit_parameters,
)

pytestmark = pytest.mark.system


async def test_create_butterfly_valve(tmp_path: Path) -> None:
    chat = await start_chat()

    result = await prompt(chat, "Create a butterfly valve.")
    expect_parameter_request(
        result,
        ["pipe_diameter", "num_holes", "hole_diameter", "rod_diameter"],
    )

    result = await submit_parameters(
        chat,
        {
            "pipe_diameter": 0.9,
            "num_holes": 4,
            "hole_diameter": 0.05,
            "rod_diameter": 0.08,
        },
    )

    assert result.status == "completed", result.text
    assert len(result.artifacts) == 2
    assert {artifact.type for artifact in result.artifacts} == {
        "application/step",
        "application/stl",
    }
    downloads = [await chat.download(artifact, tmp_path / artifact.name) for artifact in result.artifacts]
    assert all(download.stat().st_size > 0 for download in downloads)
    await expect_similar(
        result.text,
        "Equipment geometry was authored and STEP and STL outputs are available.",
    )


async def test_create_revise_and_mesh_butterfly_valve() -> None:
    chat = await start_chat()

    result = await prompt(
        chat,
        ("Create a butterfly valve with a pipe diameter of 0.9 m, 4 holes, and a hole diameter of 0.05 m."),
    )
    expect_parameter_request(result, ["rod_diameter"])

    result = await submit_parameters(chat, {"rod_diameter": 0.08})
    assert result.status == "completed", result.text
    assert {artifact.type for artifact in result.new_artifacts} == {
        "application/step",
        "application/stl",
    }

    result = await prompt(chat, "Double the hole diameter and then mesh it.")

    assert result.status == "completed", result.text
    assert {artifact.type for artifact in result.new_artifacts} >= {
        "application/step",
        "application/stl",
        "application/x-exodus",
    }
    await expect_similar(
        result.text,
        "Equipment geometry was authored and an Exodus mesh was generated.",
    )


async def test_create_and_mesh_continues_after_parameter_request() -> None:
    chat = await start_chat()

    result = await prompt(
        chat,
        (
            "Create a butterfly valve with a pipe diameter of 0.9 m, 4 holes, "
            "and a hole diameter of 0.05 m, then mesh it."
        ),
    )
    expect_parameter_request(result, ["rod_diameter"])

    result = await submit_parameters(chat, {"rod_diameter": 0.08})

    assert result.status == "completed", result.text
    assert {artifact.type for artifact in result.new_artifacts} >= {
        "application/step",
        "application/stl",
        "application/x-exodus",
    }
    await expect_similar(
        result.text,
        "Equipment geometry was authored and an Exodus mesh was generated.",
    )
