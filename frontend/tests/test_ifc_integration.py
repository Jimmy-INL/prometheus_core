"""Tests for components/ifc_integration.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from components.ifc_integration import IFCDataset, format_file_size, process_ifc_upload


# --- format_file_size ---


def test_format_file_size_bytes():
    assert format_file_size(512) == "512 B"
    assert format_file_size(0) == "0 B"


def test_format_file_size_kb():
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1536) == "1.5 KB"


def test_format_file_size_mb():
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(int(2.5 * 1024 * 1024)) == "2.5 MB"


def test_format_file_size_gb():
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"


# --- IFCDataset ---


def _make_dataset() -> IFCDataset:
    return IFCDataset(
        dataset_id="abcd1234",
        source_path=Path("/uploads/model.ifc"),
        output_dir=Path("/public/ifc-data/abcd1234"),
        filename="model.ifc",
        file_size=2048,
    )


def test_ifc_dataset_file_url():
    ds = _make_dataset()
    assert ds.file_url == "/public/ifc-data/abcd1234/model.ifc"


def test_ifc_dataset_to_props():
    ds = _make_dataset()
    props = ds.to_props()
    assert props["datasetId"] == "abcd1234"
    assert props["fileUrl"] == "/public/ifc-data/abcd1234/model.ifc"
    assert props["filename"] == "model.ifc"
    assert props["height"] == "500px"


def test_ifc_dataset_to_result_dict():
    ds = _make_dataset()
    d = ds.to_result_dict()
    assert d["_type"] == "ifc_dataset"
    assert d["dataset_id"] == "abcd1234"
    assert d["file_url"] == "/public/ifc-data/abcd1234/model.ifc"
    assert d["file_size"] == 2048


# --- process_ifc_upload ---


@pytest.mark.asyncio
async def test_process_ifc_upload(tmp_path: Path):
    """File is copied to ifc_data_dir and IFCDataset is returned."""
    # Create a fake IFC file
    src = tmp_path / "uploads" / "building.ifc"
    src.parent.mkdir()
    src.write_text("IFC content")

    ifc_output = tmp_path / "ifc-data"
    ifc_output.mkdir()

    with patch("components.ifc_integration.settings") as mock_settings:
        mock_settings.ifc_data_dir = ifc_output
        result = await process_ifc_upload(src)

    assert isinstance(result, IFCDataset)
    assert result.filename == "building.ifc"
    assert result.file_size == len("IFC content")
    # Verify file was actually copied
    dest = result.output_dir / "building.ifc"
    assert dest.exists()
    assert dest.read_text() == "IFC content"
