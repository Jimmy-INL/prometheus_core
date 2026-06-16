"""Tests for visualization plugin routing."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import plugins


def test_find_plugin_for_typed_thermal_analysis_json_artifact() -> None:
    plugin = plugins.find_plugin_for_artifact(
        {
            "mime_type": "application/json",
            "json_type": "prometheus.thermal_analysis.result.v1",
            "json_body": {"material_id": "SS316", "status": "acceptable"},
        }
    )

    assert plugin is not None
    assert plugin.COMPONENT_NAME == "ThermalAnalysisViewer"


def test_extension_fallback_routes_mislabeled_stl_by_name() -> None:
    # No json_type, an unregistered/informal MIME — must still route via the
    # .stl extension on the artifact name.
    plugin = plugins.find_plugin_for_artifact(
        {"name": "equipment_abc.stl", "mime_type": "application/octet-stream", "uri": "file:///x"}
    )
    assert plugin is not None and plugin.COMPONENT_NAME == "MeshViewer"


def test_extension_fallback_routes_by_uri_when_name_has_no_suffix() -> None:
    plugin = plugins.find_plugin_for_artifact(
        {"name": "mesh", "uri": "deeplynx://organizations/o/items/part.stl?v=2"}
    )
    assert plugin is not None and plugin.COMPONENT_NAME == "MeshViewer"


def test_mime_takes_precedence_over_extension() -> None:
    # A registered MIME wins even if the extension would map elsewhere.
    plugin = plugins.find_plugin_for_artifact({"name": "thing.stl", "mime_type": "application/ifc"})
    assert plugin is not None and plugin.COMPONENT_NAME == "IFCViewer"


def test_unknown_extension_returns_none() -> None:
    assert plugins.find_plugin_for_artifact({"name": "data.json", "mime_type": "application/json"}) is None


@pytest.mark.asyncio
async def test_inspect_upload_uses_mime_type_for_temp_paths(tmp_path: Path) -> None:
    upload_path = tmp_path / "chainlit-upload"
    upload_path.write_bytes(b"not inspected")

    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=upload_path,
            display_name="mesh.e",
            mime_type="application/x-exodus",
            size_bytes=13,
        )
    )

    assert match is not None
    assert match.mime_type == "application/x-exodus"
    assert match.plugin.COMPONENT_NAME == "MeshViewer"


@pytest.mark.asyncio
async def test_inspect_upload_does_not_dispatch_generic_mime_by_filename_only(tmp_path: Path) -> None:
    upload_path = tmp_path / "chainlit-upload"
    upload_path.write_bytes(b"plain text")

    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=upload_path,
            display_name="cahnhilliard_out.e",
            mime_type="application/octet-stream",
            size_bytes=10,
        )
    )

    assert match is None


@pytest.mark.asyncio
async def test_inspect_upload_identifies_ifc_despite_text_plain_mime(tmp_path: Path) -> None:
    upload_path = tmp_path / "chainlit-upload"
    upload_path.write_text("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\n", encoding="utf-8")

    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=upload_path,
            display_name="building.ifc",
            mime_type="text/plain",
            size_bytes=upload_path.stat().st_size,
        )
    )

    assert match is not None
    assert match.mime_type == "model/ifc"
    assert match.plugin.COMPONENT_NAME == "IFCViewer"


@pytest.mark.asyncio
async def test_inspect_upload_tie_breaks_by_plugin_name(monkeypatch, tmp_path: Path) -> None:
    upload_path = tmp_path / "sample.bin"
    upload_path.write_bytes(b"sample")
    plugin_a = SimpleNamespace(
        __name__="plugins.alpha",
        MIMETYPES=["application/x-alpha"],
        inspect_upload=lambda context: plugins.UploadMatch(
            mime_type="application/x-alpha",
            confidence=50,
        ),
    )
    plugin_b = SimpleNamespace(
        __name__="plugins.beta",
        MIMETYPES=["application/x-beta"],
        inspect_upload=lambda context: plugins.UploadMatch(
            mime_type="application/x-beta",
            confidence=50,
        ),
    )
    monkeypatch.setattr(plugins, "_upload_plugins", [plugin_b, plugin_a])

    match = await plugins.inspect_upload(
        plugins.UploadContext(
            file_path=upload_path,
            display_name="sample.bin",
            mime_type="application/octet-stream",
            size_bytes=6,
        )
    )

    assert match is not None
    assert match.plugin is plugin_a
