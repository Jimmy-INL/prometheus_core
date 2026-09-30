"""Per-turn artifact ids on the stored conversation history.

A restored conversation renders each assistant turn from the ids stamped on its own
history entry, never from the whole conversation catalog (Prometheus Artifact
Contract, "Frontend viewer ownership").
"""

import conversation_store
from conversation_store import record_turn_artifacts, stamp_turn_artifacts


def _history():
    return [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply one", "type": "final_report"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply two", "type": "agent_response_x"},
        {"role": "assistant", "content": "reply two", "type": "final_report"},
    ]


def test_stamps_the_newest_entry_whose_content_is_the_reply():
    history = _history()

    assert stamp_turn_artifacts(history, ["a1", "a2"], ["reply one"]) is True

    assert history[1]["artifact_ids"] == ["a1", "a2"]
    assert all("artifact_ids" not in e for i, e in enumerate(history) if i != 1)


def test_a_reply_logged_twice_is_stamped_on_its_last_copy():
    history = _history()

    stamp_turn_artifacts(history, ["m1"], [None, "reply two", ""])

    assert "artifact_ids" not in history[3]
    assert history[4]["artifact_ids"] == ["m1"]


def test_no_matching_reply_stamps_nothing():
    # A plan rejection or the "running in the background" notice writes no history
    # entry; this turn's artifacts must not land under an older reply.
    history = _history()

    assert stamp_turn_artifacts(history, ["a1"], ["This is taking a while"]) is False
    assert all("artifact_ids" not in e for e in history)


def test_no_new_artifacts_or_no_reply_text_changes_nothing():
    history = _history()

    assert stamp_turn_artifacts(history, [], ["reply one"]) is False
    assert stamp_turn_artifacts(history, [None, ""], ["reply one"]) is False
    assert stamp_turn_artifacts(history, ["a1"], [None, ""]) is False
    assert all("artifact_ids" not in e for e in history)


def test_a_second_stamp_keeps_existing_ids_and_skips_duplicates():
    history = _history()
    stamp_turn_artifacts(history, ["a1"], ["reply one"])

    assert stamp_turn_artifacts(history, ["a1", "a2"], ["reply one"]) is True
    assert history[1]["artifact_ids"] == ["a1", "a2"]
    assert stamp_turn_artifacts(history, ["a2"], ["reply one"]) is False


def test_record_turn_artifacts_writes_the_stamped_document_back(monkeypatch):
    stored = {"c1": {"user_query": "first", "conversation_history": _history()}}
    writes = []
    monkeypatch.setattr(conversation_store, "get_conversation", lambda cid: stored.get(cid))
    monkeypatch.setattr(conversation_store, "store_conversation", lambda cid, state: writes.append((cid, state)))

    record_turn_artifacts("c1", ["a1"], ["reply one"])

    ((cid, state),) = writes
    assert cid == "c1"
    assert state["conversation_history"][1]["artifact_ids"] == ["a1"]
    assert state["user_query"] == "first"


def test_record_turn_artifacts_skips_the_write_when_nothing_changes(monkeypatch):
    writes = []
    monkeypatch.setattr(conversation_store, "get_conversation", lambda cid: {"conversation_history": _history()} if cid == "c1" else None)
    monkeypatch.setattr(conversation_store, "store_conversation", lambda cid, state: writes.append(cid))

    record_turn_artifacts("c1", ["a1"], ["no such reply"])
    record_turn_artifacts("missing", ["a1"], ["reply one"])

    assert writes == []
