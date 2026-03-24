"""Tests for frontend A2A response extraction."""

import json
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from utils.a2a_client import A2AClient


def test_parse_response_extracts_conversation_response_from_data_artifact() -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    payload = {
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
    }

    result = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "kind": "text",
                            "text": json.dumps(payload),
                        }
                    ]
                }
            }
        }
    }

    response = client._parse_response(result, "fallback-conv")

    assert response.status == "completed"
    assert response.message == "SVG artifact created successfully."
    assert response.new_artifacts is not None
    assert response.new_artifacts[0]["name"] == "prometheus.svg"


def test_parse_response_extracts_from_rooted_text_part() -> None:
    client = A2AClient(agent_url="http://example.test", agent_secret="secret")
    payload = {
        "conversation_id": "conv-1",
        "status": "needs_info",
        "message": "I need the operating temperature.",
        "followup_questions": [
            {
                "field": "context.temperature_c",
                "question": "Operating temperature in Celsius",
                "type": "number",
            }
        ],
    }

    result = {
        "result": {
            "status": {
                "message": {
                    "parts": [
                        {
                            "root": {
                                "kind": "text",
                                "text": json.dumps(payload),
                            }
                        }
                    ]
                }
            }
        }
    }

    response = client._parse_response(result, "fallback-conv")

    assert response.status == "needs_info"
    assert response.followup_questions is not None
    assert response.followup_questions[0]["field"] == "context.temperature_c"
