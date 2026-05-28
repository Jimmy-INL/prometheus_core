"""Tests for components/exodus/models.py and exceptions.py."""

from pathlib import Path

from components.exodus.exceptions import (
    ConversionError,
    ConverterError,
    FileNotFoundError,
    InvalidExodusFileError,
    UnsupportedFeatureError,
)
from components.exodus.models import ConvertRequest, ConvertResult, ExodusMetadata


# --- ConvertRequest ---


def test_convert_request_defaults():
    """Default values are set correctly."""
    req = ConvertRequest(input_path=Path("/in.exo"), output_dir=Path("/out"))
    assert req.representation == "surface"
    assert req.timestep_mode == "all"
    assert req.compress is True
    assert req.include_normals is True
    assert req.normal_style == "flat"
    assert req.blocks is None
    assert req.variables is None
    assert req.decimate is None


def test_convert_request_path_coercion():
    """String paths are converted to Path objects in __post_init__."""
    req = ConvertRequest(input_path="/in.exo", output_dir="/out")  # type: ignore[arg-type]
    assert isinstance(req.input_path, Path)
    assert isinstance(req.output_dir, Path)


# --- ConvertResult ---


def test_convert_result_creation():
    """Basic construction works."""
    result = ConvertResult(
        dataset_id="abc123",
        output_dir=Path("/out"),
        manifest_path=Path("/out/manifest.json"),
        metadata={"num_timesteps": 5},
    )
    assert result.dataset_id == "abc123"
    assert result.metadata["num_timesteps"] == 5


def test_convert_result_default_metadata():
    """Metadata defaults to empty dict."""
    result = ConvertResult(
        dataset_id="x",
        output_dir=Path("/out"),
        manifest_path=Path("/out/manifest.json"),
    )
    assert result.metadata == {}


# --- ExodusMetadata ---


def _make_metadata() -> ExodusMetadata:
    return ExodusMetadata(
        num_timesteps=3,
        time_values=[0.0, 0.5, 1.0],
        nodal_variables=["temp", "disp_x"],
        element_variables=["stress"],
        global_variables=[],
        element_blocks=[{"id": 1, "name": "block_1"}],
        bounds=(0.0, 1.0, 0.0, 2.0, 0.0, 3.0),
        num_nodes=100,
        num_elements=50,
    )


def test_exodus_metadata_to_dict():
    """to_dict returns a JSON-serializable dict with bounds as list."""
    m = _make_metadata()
    d = m.to_dict()
    assert d["num_timesteps"] == 3
    assert d["bounds"] == [0.0, 1.0, 0.0, 2.0, 0.0, 3.0]
    assert isinstance(d["bounds"], list)
    assert d["nodal_variables"] == ["temp", "disp_x"]


def test_exodus_metadata_to_dict_roundtrip():
    """All fields survive the to_dict conversion."""
    m = _make_metadata()
    d = m.to_dict()
    assert set(d.keys()) == {
        "num_timesteps",
        "time_values",
        "nodal_variables",
        "element_variables",
        "global_variables",
        "element_blocks",
        "bounds",
        "num_nodes",
        "num_elements",
    }


# --- Exceptions ---


def test_converter_error_hierarchy():
    """All custom exceptions inherit from ConverterError."""
    for exc_class in (FileNotFoundError, InvalidExodusFileError, ConversionError, UnsupportedFeatureError):
        assert issubclass(exc_class, ConverterError)


def test_exceptions_are_catchable_by_base():
    """Raising a subclass is caught by the base ConverterError."""
    with __import__("pytest").raises(ConverterError):
        raise InvalidExodusFileError("bad file")


def test_exception_message():
    """Exception message is preserved."""
    e = ConversionError("pipeline failed")
    assert str(e) == "pipeline failed"
