"""Tests for visualization plugin routing."""

import sys
from pathlib import Path

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


def test_find_plugin_for_upload_uses_mime_type_for_temp_paths() -> None:
    plugin = plugins.find_plugin_for_upload(
        Path("/tmp/chainlit-upload"),
        mime_type="application/x-exodus",
    )

    assert plugin is not None
    assert plugin.COMPONENT_NAME == "ExodusViewer"


def test_find_plugin_for_upload_does_not_dispatch_generic_mime_by_filename() -> None:
    plugin = plugins.find_plugin_for_upload(
        Path("/tmp/cahnhilliard_out.e"),
        mime_type="application/octet-stream",
    )

    assert plugin is None
