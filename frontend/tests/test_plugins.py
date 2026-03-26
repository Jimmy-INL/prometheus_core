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
