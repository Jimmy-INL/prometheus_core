"""Data models for the converter library."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ConvertRequest:
    """Request parameters for Exodus II conversion."""

    input_path: Path
    output_dir: Path
    representation: Literal["surface", "volume"] = "surface"
    blocks: list[str] | None = None
    variables: list[str] | None = None
    timestep_mode: Literal["single", "all", "stride"] = "all"
    timestep_index: int | None = None
    timestep_stride: int | None = None
    decimate: float | None = None
    compress: bool = True
    include_normals: bool = True

    def __post_init__(self) -> None:
        """Validate and convert paths."""
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
        """Convert to dictionary for JSON serialization."""
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
