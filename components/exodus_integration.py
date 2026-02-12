"""
Exodus II integration for Chainlit.

Provides utilities to convert Exodus II files and create viewer components.
Includes async wrappers for VTK operations to avoid blocking the event loop.
"""

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chainlit as cl

from .exodus import convert_exodus, inspect_exodus, ConvertRequest, ConvertResult
from utils.settings import settings


# Dedicated thread pool for VTK operations (CPU-bound)
# Limited to 2 workers to avoid memory issues with large meshes
_vtk_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vtk-")


@dataclass
class ExodusDataset:
    """
    Represents a converted Exodus II dataset ready for visualization.
    """

    dataset_id: str
    source_path: Path
    output_dir: Path
    metadata: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        """URL base path for accessing dataset files."""
        return f"/public/exodus-data/{self.dataset_id}"

    def to_props(self) -> dict[str, Any]:
        """Convert to props dict for ExodusViewer component."""
        # Determine initial variable
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
            name="ExodusViewer",
            props=self.to_props(),
            display="inline",
        )

    def to_result_dict(self) -> dict[str, Any]:
        """
        Create a structured result dict for agent tool returns.

        This format is recognized by on_tool_result() in chainlit_callbacks.py.
        """
        return {
            "_type": "exodus_dataset",
            "dataset_id": self.dataset_id,
            "base_url": self.base_url,
            "metadata": self.metadata,
            "manifest": self.manifest,
        }


def inspect_exodus_file(file_path: Path) -> dict:
    """
    Inspect an Exodus II file and return metadata without converting.

    Args:
        file_path: Path to the Exodus II file.

    Returns:
        Dictionary with file metadata including timesteps, variables, bounds, etc.
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    return inspect_exodus(file_path)


async def inspect_exodus_file_async(file_path: Path) -> dict:
    """
    Async wrapper for inspect_exodus_file.

    Runs VTK inspection in a dedicated thread pool to avoid blocking.

    Args:
        file_path: Path to the Exodus II file.

    Returns:
        Dictionary with file metadata.
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_vtk_executor, lambda: inspect_exodus(file_path))


def _convert_exodus_sync(
    file_path: Path,
    output_dir: Path,
    representation: str,
    cache_root: Path | None,
) -> ConvertResult:
    """
    Synchronous conversion helper for use in thread pool.

    Args:
        file_path: Path to the Exodus II file.
        output_dir: Output directory for converted files.
        representation: "surface" or "volume" representation.
        cache_root: Optional cache root directory.

    Returns:
        ConvertResult from conversion.
    """
    request = ConvertRequest(
        input_path=file_path,
        output_dir=output_dir,
        representation=representation,
        timestep_mode="all",
        compress=True,
        include_normals=True,
    )
    return convert_exodus(request, cache_root=cache_root)


async def process_exodus_upload(
    file_path: Path,
    output_dir: Path | None = None,
    representation: str = "surface",
    cache: bool = True,
) -> ExodusDataset:
    """
    Process an uploaded Exodus II file for visualization.

    Converts the file to VTP format in a dedicated thread pool to avoid
    blocking the event loop. Large files can take significant time to process.

    Args:
        file_path: Path to the uploaded Exodus II file.
        output_dir: Optional custom output directory. Defaults to public/exodus-data/{id}.
        representation: "surface" or "volume" representation.
        cache: Whether to use caching for conversion.

    Returns:
        ExodusDataset instance ready for visualization.
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Generate dataset ID
    dataset_id = str(uuid.uuid4())[:8]

    # Determine output directory
    if output_dir is None:
        output_dir = settings.exodus_data_dir / dataset_id

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine cache root
    cache_root = settings.exodus_data_dir if cache else None

    # Run conversion in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    result: ConvertResult = await loop.run_in_executor(
        _vtk_executor, lambda: _convert_exodus_sync(file_path, output_dir, representation, cache_root)
    )

    # If cached result was in different location, use cached values
    if result.output_dir != output_dir:
        dataset_id = result.dataset_id
        output_dir = result.output_dir

    # Load manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    return ExodusDataset(
        dataset_id=dataset_id,
        source_path=file_path,
        output_dir=output_dir,
        metadata=result.metadata,
        manifest=manifest,
    )


def create_exodus_viewer_result(
    dataset_id: str,
    base_url: str,
    metadata: dict,
    manifest: dict,
) -> dict[str, Any]:
    """
    Create a structured result dict for exodus visualization.

    This is a convenience function for agents to create properly formatted
    exodus dataset results that will be rendered by the Chainlit callbacks.

    Args:
        dataset_id: Unique identifier for the dataset.
        base_url: URL base path for accessing dataset files.
        metadata: Dataset metadata (timesteps, variables, bounds, etc.).
        manifest: File manifest with VTP file listings.

    Returns:
        Structured dict with _type: "exodus_dataset".
    """
    return {
        "_type": "exodus_dataset",
        "dataset_id": dataset_id,
        "base_url": base_url,
        "metadata": metadata,
        "manifest": manifest,
    }
