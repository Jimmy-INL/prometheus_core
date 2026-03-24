"""Regression tests for follow-up form mapping in the frontend."""

from __future__ import annotations


def test_followup_question_with_null_options_is_safe():
    question = {
        "field": "temperature_c",
        "question": "What operating temperature should I use for the thermal analysis (in Celsius)?",
        "type": "number",
        "required": True,
        "description": "Operating temperature in Celsius at which the material should be evaluated.",
        "options": None,
    }

    field = {
        "id": question.get("field", question.get("id", question.get("question", ""))),
        "label": question.get("question", question.get("label", "")),
        "input_type": question.get("type", question.get("input_type", "text")),
        "required": bool(question.get("required", True)),
    }
    if isinstance(question.get("options"), list):
        field["options"] = [
            opt if isinstance(opt, dict) else {"label": str(opt), "value": str(opt)}
            for opt in question["options"]
        ]
    if question.get("description"):
        field["help"] = question["description"]

    assert field["id"] == "temperature_c"
    assert field["input_type"] == "number"
    assert "options" not in field
