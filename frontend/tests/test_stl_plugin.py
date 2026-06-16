"""Tests for STL rendering via the shared VTK/MeshViewer pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import vtk

import plugins
from components import stl_integration


def _write_cube_stl(path: Path) -> None:
    """Write a small valid binary STL (a cube → 12 triangles) using VTK."""
    cube = vtk.vtkCubeSource()
    cube.Update()
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(cube.GetOutputPort())
    writer.SetFileTypeToBinary()
    writer.Write()


# --- conversion --------------------------------------------------------------


def test_convert_stl_produces_exodus_shaped_output(tmp_path: Path) -> None:
    stl = tmp_path / "cube.stl"
    _write_cube_stl(stl)
    out = tmp_path / "out"

    metadata = stl_integration._convert_stl_sync(stl, out)

    # Same output contract as the Exodus pipeline.
    assert (out / "surface_t0000.vtp").exists()
    assert (out / "manifest.json").exists()
    assert (out / "meta.json").exists()

    assert metadata["num_timesteps"] == 1
    assert metadata["num_elements"] > 0  # triangles
    assert metadata["num_nodes"] > 0
    assert metadata["nodal_variables"] == []
    assert metadata["element_variables"] == []
    assert len(metadata["bounds"]) == 6


def test_convert_stl_manifest_is_single_timestep_no_variables(tmp_path: Path) -> None:
    import json

    stl = tmp_path / "cube.stl"
    _write_cube_stl(stl)
    out = tmp_path / "out"
    stl_integration._convert_stl_sync(stl, out)

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["num_timesteps"] == 1
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["filename"] == "surface_t0000.vtp"
    assert manifest["variables"] == {"point": [], "cell": []}


def test_inspect_stl_counts_and_rejects_non_stl(tmp_path: Path) -> None:
    stl = tmp_path / "cube.stl"
    _write_cube_stl(stl)
    info = stl_integration.inspect_stl(stl)
    assert info["num_elements"] > 0

    junk = tmp_path / "notstl.bin"
    junk.write_bytes(b"this is definitely not an STL file")
    with pytest.raises(stl_integration.InvalidSTLFileError):
        stl_integration.inspect_stl(junk)


# --- plugin routing ----------------------------------------------------------


@pytest.mark.parametrize(
    "mime",
    [
        "model/stl",
        "application/stl",  # what agents commonly emit (regression: was "no viewer available")
        "application/x-stl",
        "application/sla",
        "application/vnd.ms-pki.stl",
    ],
)
def test_stl_plugin_registered_for_mime(mime: str) -> None:
    # Agent-emitted artifacts dispatch purely by mime_type, so every STL mime
    # variant we accept must route to the viewer.
    plugin = plugins.find_plugin_for_artifact({"mime_type": mime})
    assert plugin is not None, f"no plugin for {mime}"
    assert plugin.COMPONENT_NAME == "MeshViewer"  # reuses the shared viewer


@pytest.mark.asyncio
async def test_inspect_upload_matches_declared_stl_mime(tmp_path: Path) -> None:
    upload = tmp_path / "chainlit-upload"
    upload.write_bytes(b"not inspected for declared MIME")
    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=upload,
            display_name="part.stl",
            mime_type="model/stl",
            size_bytes=upload.stat().st_size,
        )
    )
    assert match is not None
    assert match.mime_type == "model/stl"
    assert match.plugin is not None and match.plugin.COMPONENT_NAME == "MeshViewer"


@pytest.mark.asyncio
async def test_inspect_upload_confirms_generic_mime_by_reading(tmp_path: Path) -> None:
    stl = tmp_path / "part.stl"
    _write_cube_stl(stl)
    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=stl,
            display_name="part.stl",
            mime_type="application/octet-stream",  # generic; must be confirmed by reading
            size_bytes=stl.stat().st_size,
        )
    )
    assert match is not None
    assert match.mime_type == "model/stl"
