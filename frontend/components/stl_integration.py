"""STL mesh integration for Chainlit.

STL is the simplest case of the existing Exodus VTK pipeline: a single static
surface with no timesteps and no field variables. So an STL file is converted to
exactly the same VTP + ``manifest.json`` + ``meta.json`` output the Exodus path
produces and rendered by the **same** ``ExodusViewer`` element (which already
degrades to "one timestep, no variables" — it just shows the geometry).

This module reuses the Exodus pipeline's polydata helpers (`clean_polydata`,
`compute_normals`, `write_vtp`), the content-hash cache, and the `ExodusDataset`
wrapper; it only swaps the reader (`vtkSTLReader`) and the metadata extraction.

(Step B will generalize the Exodus-named types into a neutral mesh viewer; this
module deliberately reuses them as-is for now.)
"""

import asyncio
import json
import uuid
from pathlib import Path

import vtk

from utils.settings import settings

from .exodus.cache import compute_dataset_id, get_cache_path, is_cached
from .exodus.vtk_pipeline import clean_polydata, compute_normals, write_vtp
from .exodus_integration import ExodusDataset, _vtk_executor


class InvalidSTLFileError(Exception):
    """Raised when a file cannot be read as STL."""


def _read_stl_polydata(file_path: Path) -> "vtk.vtkPolyData":
    """Read an STL file into polydata, validating it actually contains triangles.

    `vtkSTLReader` handles both ASCII and binary STL. A non-STL file typically
    yields zero cells, which we treat as "not an STL".
    """
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(file_path))
    reader.Update()
    polydata = reader.GetOutput()
    if polydata is None or polydata.GetNumberOfCells() == 0:
        raise InvalidSTLFileError(f"No triangles read from STL file: {file_path}")
    return polydata


def _bounds(polydata: "vtk.vtkPolyData") -> list[float]:
    bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    polydata.GetBounds(bounds)
    return list(bounds)


def inspect_stl(file_path: Path) -> dict:
    """Read an STL file's geometry counts/bounds without writing output.

    Raises ``InvalidSTLFileError`` if the file is not a readable STL — used by the
    plugin's upload inspector to confirm a candidate file.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise InvalidSTLFileError(f"File not found: {file_path}")
    try:
        polydata = _read_stl_polydata(file_path)
    except InvalidSTLFileError:
        raise
    except Exception as exc:  # vtk surfaces a variety of errors on bad input
        raise InvalidSTLFileError(f"Failed to read STL file: {exc}") from exc
    return {
        "num_timesteps": 1,
        "num_nodes": polydata.GetNumberOfPoints(),
        "num_elements": polydata.GetNumberOfCells(),
        "bounds": _bounds(polydata),
        "nodal_variables": [],
        "element_variables": [],
    }


async def inspect_stl_file_async(file_path: Path) -> dict:
    """Async wrapper for :func:`inspect_stl` (runs in the shared VTK thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_vtk_executor, lambda: inspect_stl(Path(file_path)))


def _build_manifest_and_meta(polydata: "vtk.vtkPolyData") -> tuple[dict, dict]:
    bounds = _bounds(polydata)
    manifest = {
        "version": "1.0",
        "num_timesteps": 1,
        "files": [{"index": 0, "timestep_index": 0, "time_value": 0.0, "filename": "surface_t0000.vtp"}],
        "variables": {"point": [], "cell": []},
        "array_ranges": {},
        "bounds": bounds,
    }
    metadata = {
        "num_timesteps": 1,
        "time_values": [0.0],
        "nodal_variables": [],
        "element_variables": [],
        "global_variables": [],
        "element_blocks": [],
        "bounds": bounds,
        "num_nodes": polydata.GetNumberOfPoints(),
        "num_elements": polydata.GetNumberOfCells(),
    }
    return manifest, metadata


def _convert_stl_sync(file_path: Path, output_dir: Path) -> dict:
    """Convert an STL file to a single VTP plus manifest/meta. Returns the metadata.

    Mirrors the output contract of ``exodus.vtk_pipeline.run_conversion`` so the
    result renders identically in ``ExodusViewer``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    polydata = _read_stl_polydata(file_path)
    # STL is already a triangle surface; clean merges duplicate vertices and
    # compute_normals gives correct shading (STL normals are unreliable).
    polydata = clean_polydata(polydata)
    polydata = compute_normals(polydata, style="flat")
    write_vtp(polydata, output_dir / "surface_t0000.vtp", compress=True)

    manifest, metadata = _build_manifest_and_meta(polydata)
    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    with open(output_dir / "meta.json", "w") as f:
        json.dump(metadata, f, indent=2)
    return metadata


async def process_stl_upload(
    file_path: Path,
    output_dir: Path | None = None,
    cache: bool = True,
) -> ExodusDataset:
    """Convert an STL file (upload or agent artifact) into a renderable dataset.

    Runs the VTK conversion off the event loop in the shared thread pool, reuses
    the content-hash cache, and returns an ``ExodusDataset`` whose
    ``to_chainlit_element()`` yields the shared ``ExodusViewer``.
    """
    file_path = Path(file_path)

    cache_root = settings.exodus_data_dir if cache else None
    if cache_root is not None:
        dataset_id = compute_dataset_id(file_path, {"type": "stl"})
        resolved_dir = get_cache_path(cache_root, dataset_id)
        if is_cached(cache_root, dataset_id):
            with open(resolved_dir / "manifest.json") as f:
                manifest = json.load(f)
            with open(resolved_dir / "meta.json") as f:
                metadata = json.load(f)
            return ExodusDataset(
                dataset_id=dataset_id,
                source_path=file_path,
                output_dir=resolved_dir,
                metadata=metadata,
                manifest=manifest,
            )
    else:
        dataset_id = str(uuid.uuid4())[:8]
        resolved_dir = output_dir or (settings.exodus_data_dir / dataset_id)

    loop = asyncio.get_event_loop()
    metadata = await loop.run_in_executor(_vtk_executor, lambda: _convert_stl_sync(file_path, resolved_dir))
    with open(resolved_dir / "manifest.json") as f:
        manifest = json.load(f)

    return ExodusDataset(
        dataset_id=dataset_id,
        source_path=file_path,
        output_dir=resolved_dir,
        metadata=metadata,
        manifest=manifest,
    )
