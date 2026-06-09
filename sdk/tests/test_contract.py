"""Tests for the frontend <-> client-agent wire contract models."""

import json

import pytest
from pydantic import ValidationError

from prometheus_api.agent.contract import (
    ConversationRequest,
    ConversationResponse,
    ConversationStatus,
)


def test_status_values_are_exhaustive():
    assert set(ConversationStatus.values()) == {
        "needs_info",
        "plan_ready",
        "executing",
        "completed",
        "recommendation",
        "answer",
        "backgrounded",
        "error",
    }


def test_response_round_trips_through_json():
    response = ConversationResponse(
        conversation_id="conv-1",
        status=ConversationStatus.COMPLETED,
        report="All done.",
        artifacts=[{"artifact_id": "a-1"}],
    )
    payload = json.loads(json.dumps(response.model_dump()))
    parsed = ConversationResponse.from_payload(payload)
    assert parsed.status == "completed"
    assert parsed.conversation_id == "conv-1"
    assert parsed.report == "All done."
    assert parsed.artifacts == [{"artifact_id": "a-1"}]


def test_response_status_is_plain_string_after_validation():
    response = ConversationResponse(conversation_id="c", status="answer")
    assert response.status == "answer"
    assert isinstance(response.status, str)
    # json.dumps must not choke on the status field
    json.dumps(response.model_dump())


def test_response_rejects_unknown_status():
    with pytest.raises(ValidationError):
        ConversationResponse(conversation_id="c", status="success")


def test_response_defaults():
    parsed = ConversationResponse.from_payload({})
    assert parsed.conversation_id == ""
    assert parsed.status == "answer"
    assert parsed.followup_questions is None


def test_response_ignores_unknown_fields():
    parsed = ConversationResponse.from_payload(
        {"conversation_id": "c", "status": "answer", "some_future_field": 1}
    )
    assert parsed.conversation_id == "c"
    assert not hasattr(parsed, "some_future_field")


def test_request_round_trip_and_defaults():
    request = ConversationRequest(query="analyze SS316", conversation_id="conv-2")
    payload = json.loads(json.dumps(request.model_dump()))
    parsed = ConversationRequest.model_validate(payload)
    assert parsed.query == "analyze SS316"
    assert parsed.plan_approved is False
    assert parsed.plan_rejected is False
    assert parsed.uploaded_files is None
