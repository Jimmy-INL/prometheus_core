"""Tests for frontend A2A response extraction."""

import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from utils.a2a_client import A2AClient


def test_parse_response_extracts_conversation_response_from_data_artifact() -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")

    result = {
        "result": {
            "artifacts": [
                {
                    "artifactId": "result-artifact",
                    "name": "result",
                    "parts": [
                        {
                            "kind": "data",
                            "data": {
                                "conversation_id": "conv-1",
                                "status": "completed",
                                "message": "SVG artifact created successfully.",
                                "new_artifacts": [
                                    {
                                        "artifact_id": "artifact-1",
                                        "conversation_id": "conv-1",
                                        "name": "prometheus.svg",
                                        "description": "Debug SVG containing the word 'prometheus'.",
                                        "uri": "http://localhost:8008/artifacts/conv-1/prometheus.svg",
                                        "mime_type": "image/svg+xml",
                                        "metadata": {"word": "prometheus"},
                                    }
                                ],
                            },
                            "metadata": {"mime_type": "application/json"},
                        }
                    ],
                }
            ]
        }
    }

    response = client._parse_response(result, "fallback-conv")

    assert response.status == "completed"
    assert response.message == "SVG artifact created successfully."
    assert response.new_artifacts is not None
    assert response.new_artifacts[0]["name"] == "prometheus.svg"
