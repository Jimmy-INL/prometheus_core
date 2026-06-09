"""Shared mesh-visualization types for the VTK pipeline.

Both the Exodus and STL paths convert their input to the same VTP + manifest/meta
output and render it through the same ``MeshViewer`` element. The neutral pieces
they share live here:

- ``_vtk_executor`` — the dedicated thread pool for CPU-bound VTK work.
- ``MeshDataset`` — a converted dataset (any source) ready for visualization.

Source-specific reading/conversion stays in ``exodus_integration`` /
``stl_integration``; they both return a ``MeshDataset``.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chainlit as cl

# Dedicated thread pool for VTK operations (CPU-bound). Limited to 2 workers to
# avoid memory pressure with large meshes. Shared by every mesh source.
_vtk_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vtk-")


@dataclass
class MeshDataset:
    """A converted mesh dataset (Exodus, STL, …) ready for visualization.

    Source-agnostic: it only carries the converted VTP output (manifest + meta)
    and renders through the shared ``MeshViewer``.
    """

    dataset_id: str
    source_path: Path
    output_dir: Path
    metadata: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    title: str = "Mesh Viewer"

    @property
    def base_url(self) -> str:
        """URL base path for accessing dataset files."""
        return f"/public/mesh-data/{self.dataset_id}"

    def to_props(self) -> dict[str, Any]:
        """Convert to props dict for the MeshViewer component."""
        initial_variable = None
        point_vars = self.manifest.get("variables", {}).get("point", [])
        cell_vars = self.manifest.get("variables", {}).get("cell", [])
        if point_vars:
            initial_variable = point_vars[0]
        elif cell_vars:
            initial_variable = cell_vars[0]

        return {
            "datasetId": self.dataset_id,
            "baseUrl": self.base_url,
            "title": self.title,
            "metadata": self.metadata,
            "manifest": self.manifest,
            "initialTimestep": 0,
            "initialVariable": initial_variable,
            "initialColorPreset": "coolToWarm",
            "height": "500px",
            "showControls": True,
            "allowPicking": True,
        }

    def to_chainlit_element(self) -> cl.CustomElement:
        """Create a Chainlit CustomElement for this dataset."""
        return cl.CustomElement(
            name="MeshViewer",
            props=self.to_props(),
            display="inline",
        )

    def to_result_dict(self) -> dict[str, Any]:
        """Structured result dict for agent tool returns."""
        return {
            "_type": "mesh_dataset",
            "dataset_id": self.dataset_id,
            "base_url": self.base_url,
            "metadata": self.metadata,
            "manifest": self.manifest,
        }
