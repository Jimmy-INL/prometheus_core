"""Tests for the shared A2A stream-consumption helpers."""

import json

import pytest

from prometheus_api.a2a_stream import (
    A2AStreamError,
    apply_stream_event,
    consume_stream_response,
    extract_status_message_text,
    merge_artifacts,
    new_task_accumulator,
)


class _FakeStreamResponse:
    def __init__(self, lines, *, content_type="application/x-ndjson"):
        self._lines = lines
        self.headers = {"content-type": content_type}

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _status_event(
    text,
    *,
    final=False,
    task_id="task-1",
    context_id="ctx-1",
    state="TASK_STATE_WORKING",
):
    if final and state == "TASK_STATE_WORKING":
        state = "TASK_STATE_COMPLETED"
    return {
        "result": {
            "statusUpdate": {
                "taskId": task_id,
                "contextId": context_id,
                "status": {
                    "state": state,
                    "message": {"parts": [{"text": text}]},
                },
            }
        }
    }


def _artifact_event(artifact):
    return {"result": {"artifactUpdate": {"artifact": artifact}}}


# ---------------------------------------------------------------------------
# extract_status_message_text
# ---------------------------------------------------------------------------


def test_extract_text_from_bare_part():
    status = {"message": {"parts": [{"text": " hello "}]}}
    assert extract_status_message_text(status) == "hello"


def test_extract_text_from_root_wrapped_part():
    status = {"message": {"parts": [{"root": {"kind": "text", "text": "wrapped"}}]}}
    assert extract_status_message_text(status) == "wrapped"


def test_extract_text_ignores_non_text_parts_and_non_dicts():
    status = {
        "message": {
            "parts": [
                "garbage",
                {"kind": "data", "data": {"x": 1}},
                {"kind": "text", "text": "found"},
            ]
        }
    }
    assert extract_status_message_text(status) == "found"
    assert extract_status_message_text(None) == ""
    assert extract_status_message_text({}) == ""


# ---------------------------------------------------------------------------
# merge_artifacts
# ---------------------------------------------------------------------------


def test_merge_artifacts_dedupes_by_artifact_id_then_name():
    existing = [{"artifactId": "a-1", "name": "one"}, {"name": "keyed-by-name"}]
    incoming = [
        {"artifactId": "a-1", "name": "duplicate"},
        {"name": "keyed-by-name"},
        {"artifactId": "a-2", "name": "two"},
        "not-a-dict",
    ]
    merged = merge_artifacts(existing, incoming)
    assert [a.get("artifactId") or a.get("name") for a in merged] == [
        "a-1",
        "keyed-by-name",
        "a-2",
    ]


def test_merge_artifacts_keeps_unkeyed_artifacts():
    merged = merge_artifacts([], [{"parts": []}, {"parts": []}])
    assert len(merged) == 2


# ---------------------------------------------------------------------------
# apply_stream_event
# ---------------------------------------------------------------------------


async def test_initial_v1_task_populates_accumulator():
    result = await apply_stream_event(
        new_task_accumulator(),
        {
            "result": {
                "task": {
                    "id": "task-1",
                    "contextId": "ctx-1",
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [{"artifactId": "a-1", "name": "input"}],
                }
            }
        },
    )

    assert result["id"] == "task-1"
    assert result["contextId"] == "ctx-1"
    assert result["status"]["state"] == "submitted"
    assert result["artifacts"] == [{"artifactId": "a-1", "name": "input"}]


async def test_status_update_accumulates_and_fires_callback():
    seen = []

    async def on_status(text):
        seen.append(text)

    result = new_task_accumulator()
    result = await apply_stream_event(
        result, _status_event("Working on it"), status_callback=on_status
    )
    result = await apply_stream_event(
        result,
        _status_event("Done", final=True, state="TASK_STATE_COMPLETED"),
        status_callback=on_status,
    )

    # Final events do not fire the status callback.
    assert seen == ["Working on it"]
    assert result["id"] == "task-1"
    assert result["contextId"] == "ctx-1"
    assert result["status"]["state"] == "completed"


async def test_heartbeat_events_are_skipped():
    result = await apply_stream_event(
        {"kind": "task", "artifacts": [], "status": {"state": "working"}},
        {"result": {"statusUpdate": {"metadata": {"heartbeat": True}, "status": {}}}},
    )
    # Accumulated status not overwritten by the empty heartbeat payload.
    assert result["status"] == {"state": "working"}


async def test_background_metadata_fires_background_callback():
    captured = []

    async def on_background(metadata):
        captured.append(metadata)

    await apply_stream_event(
        new_task_accumulator(),
        {
            "result": {
                "statusUpdate": {
                    "metadata": {"background": True, "estimate_seconds": 120},
                    "status": {},
                }
            }
        },
        background_callback=on_background,
    )
    assert captured == [{"background": True, "estimate_seconds": 120}]


async def test_error_envelope_raises():
    with pytest.raises(A2AStreamError, match="boom"):
        await apply_stream_event(new_task_accumulator(), {"error": "boom"})


async def test_non_dict_result_is_ignored():
    acc = new_task_accumulator()
    assert await apply_stream_event(acc, {"result": "noise"}) is acc


# ---------------------------------------------------------------------------
# consume_stream_response
# ---------------------------------------------------------------------------


async def test_consume_ndjson_stream():
    final_payload = {"status": "completed", "message": "ok"}
    lines = [
        json.dumps(_status_event("Step 1")),
        "",
        json.dumps(_artifact_event({"artifactId": "a-1", "name": "mesh.exo"})),
        json.dumps(
            _status_event(
                json.dumps(final_payload),
                final=True,
                state="TASK_STATE_COMPLETED",
            )
        ),
    ]
    statuses = []

    async def on_status(text):
        statuses.append(text)

    result = await consume_stream_response(_FakeStreamResponse(lines), status_callback=on_status)

    assert statuses == ["Step 1"]
    assert result["artifacts"] == [{"artifactId": "a-1", "name": "mesh.exo"}]
    assert json.loads(extract_status_message_text(result["status"])) == final_payload


async def test_consume_sse_stream_with_comments_and_multiline_data():
    event_one = json.dumps(_status_event("Working"))
    event_two = json.dumps(_status_event("Final", final=True, state="TASK_STATE_COMPLETED"))
    lines = [
        ": keepalive comment",
        f"data: {event_one[:10]}",
        f"data: {event_one[10:]}",
        "",
        f"data: {event_two}",
        # stream ends without trailing blank line — final block must still flush
    ]
    result = await consume_stream_response(
        _FakeStreamResponse(lines, content_type="text/event-stream")
    )
    assert result["status"]["state"] == "completed"


async def test_consume_rejects_unknown_content_type():
    with pytest.raises(A2AStreamError, match="content type"):
        await consume_stream_response(_FakeStreamResponse([], content_type="application/json"))
