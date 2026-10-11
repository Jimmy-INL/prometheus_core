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

"""Data models for the mesh converter library.

Ported from the old ``frontend/components/exodus/models.py``. Pure dataclasses — no
VTK import — so this module is safe to import from vtk-free code paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


@dataclass
class ConvertRequest:
    """Request parameters for Exodus II conversion."""

    input_path: Path
    output_dir: Path
    representation: Literal["surface", "volume"] = "surface"
    blocks: Optional[list[str]] = None
    variables: Optional[list[str]] = None
    timestep_mode: Literal["single", "all", "stride"] = "all"
    timestep_index: Optional[int] = None
    timestep_stride: Optional[int] = None
    decimate: Optional[float] = None
    compress: bool = True
    include_normals: bool = True
    normal_style: Literal["flat", "smooth"] = "flat"

    def __post_init__(self) -> None:
        """Coerce string paths to :class:`Path`."""
        if isinstance(self.input_path, str):
            self.input_path = Path(self.input_path)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)


@dataclass
class ConvertResult:
    """Result of an Exodus II conversion."""

    dataset_id: str
    output_dir: Path
    manifest_path: Path
    metadata: dict = field(default_factory=dict)


@dataclass
class ExodusMetadata:
    """Metadata extracted from an Exodus II file."""

    num_timesteps: int
    time_values: list[float]
    nodal_variables: list[str]
    element_variables: list[str]
    global_variables: list[str]
    element_blocks: list[dict]
    bounds: tuple[float, float, float, float, float, float]
    num_nodes: int
    num_elements: int

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dict (written as ``meta.json``)."""
        return {
            "num_timesteps": self.num_timesteps,
            "time_values": self.time_values,
            "nodal_variables": self.nodal_variables,
            "element_variables": self.element_variables,
            "global_variables": self.global_variables,
            "element_blocks": self.element_blocks,
            "bounds": list(self.bounds),
            "num_nodes": self.num_nodes,
            "num_elements": self.num_elements,
        }
