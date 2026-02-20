import pytest


# -- GET /api/sessions/{session_id} --

@pytest.mark.asyncio
async def test_get_session(client):
    """Should return session metadata for a valid session."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    session_resp = await client.get(f"/api/sessions/{session_id}")
    assert session_resp.status_code == 200
    data = session_resp.json()
    assert data["id"] == session_id
    assert data["user_id"] == "user_1"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    """Should return 404 for a nonexistent session."""
    resp = await client.get("/api/sessions/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found"


# -- GET /api/sessions/{session_id}/messages --

@pytest.mark.asyncio
async def test_get_messages_empty_after_no_chat(client):
    """A brand new session (from first chat) should have exactly 2 messages."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    assert msgs_resp.status_code == 200
    messages = msgs_resp.json()
    assert len(messages) == 2  # user + assistant


@pytest.mark.asyncio
async def test_get_messages_chronological_order(client):
    """Messages should be returned in chronological order."""
    resp1 = await client.post("/api/chat", json={
        "message": "first",
        "user_id": "user_1",
    })
    session_id = resp1.json()["session_id"]

    await client.post("/api/chat", json={
        "message": "second",
        "user_id": "user_1",
        "session_id": session_id,
    })

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    messages = msgs_resp.json()
    # Verify timestamps are non-decreasing
    timestamps = [m["created_at"] for m in messages]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_get_messages_not_found(client):
    """Should return 404 when the session doesn't exist."""
    resp = await client.get("/api/sessions/nonexistent/messages")
    assert resp.status_code == 404


# -- GET /api/sessions/{session_id}/workflow-steps --

@pytest.mark.asyncio
async def test_get_workflow_steps_none_for_chat(client):
    """A plain chat message should produce no workflow steps."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    steps_resp = await client.get(f"/api/sessions/{session_id}/workflow-steps")
    assert steps_resp.status_code == 200
    assert steps_resp.json() == []


@pytest.mark.asyncio
async def test_get_workflow_steps_after_trigger(client):
    """A workflow trigger should produce exactly one workflow step."""
    resp = await client.post("/api/chat", json={
        "message": "Run MOOSE",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    steps_resp = await client.get(f"/api/sessions/{session_id}/workflow-steps")
    assert steps_resp.status_code == 200
    steps = steps_resp.json()
    assert len(steps) == 1
    step = steps[0]
    assert step["session_id"] == session_id
    assert step["workflow_id"] is not None
    assert step["step_name"] == "workflow_triggered"
    assert step["status"] == "pending"


@pytest.mark.asyncio
async def test_get_workflow_steps_not_found(client):
    """Should return 404 when the session doesn't exist."""
    resp = await client.get("/api/sessions/nonexistent/workflow-steps")
    assert resp.status_code == 404


# -- GET /api/sessions/user/{user_id} --

@pytest.mark.asyncio
async def test_list_user_sessions_empty(client):
    """Should return empty list for a user with no sessions."""
    resp = await client.get("/api/sessions/user/nobody")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_user_sessions(client):
    """Should return all sessions for a user."""
    # Create two sessions for user_1
    await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    await client.post("/api/chat", json={
        "message": "world",
        "user_id": "user_1",
    })
    # One session for user_2
    await client.post("/api/chat", json={
        "message": "hi",
        "user_id": "user_2",
    })

    resp1 = await client.get("/api/sessions/user/user_1")
    assert resp1.status_code == 200
    assert len(resp1.json()) == 2

    resp2 = await client.get("/api/sessions/user/user_2")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1


@pytest.mark.asyncio
async def test_list_user_sessions_ordered_by_most_recent(client):
    """Sessions should be ordered most recent first."""
    # Create first session and remember its id
    r1 = await client.post("/api/chat", json={
        "message": "first",
        "user_id": "user_1",
    })
    first_id = r1.json()["session_id"]

    # Create second session
    r2 = await client.post("/api/chat", json={
        "message": "second",
        "user_id": "user_1",
    })
    second_id = r2.json()["session_id"]

    resp = await client.get("/api/sessions/user/user_1")
    sessions = resp.json()
    # Most recently updated should come first
    assert sessions[0]["id"] == second_id
    assert sessions[1]["id"] == first_id


@pytest.mark.asyncio
async def test_session_updated_at_advances(client):
    """Sending a message should update the session's updated_at timestamp."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    s1 = await client.get(f"/api/sessions/{session_id}")
    updated_1 = s1.json()["updated_at"]

    await client.post("/api/chat", json={
        "message": "again",
        "user_id": "user_1",
        "session_id": session_id,
    })

    s2 = await client.get(f"/api/sessions/{session_id}")
    updated_2 = s2.json()["updated_at"]

    assert updated_2 >= updated_1
