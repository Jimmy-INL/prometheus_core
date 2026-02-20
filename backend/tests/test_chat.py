import pytest


@pytest.mark.asyncio
async def test_chat_creates_session(client):
    """First message with no session_id should create a new session."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "chat"
    assert data["session_id"] is not None
    assert "hello" in data["response"]


@pytest.mark.asyncio
async def test_chat_reuses_session(client):
    """Passing an existing session_id should reuse that session."""
    # Create session
    resp1 = await client.post("/api/chat", json={
        "message": "first",
        "user_id": "user_1",
    })
    session_id = resp1.json()["session_id"]

    # Reuse session
    resp2 = await client.post("/api/chat", json={
        "message": "second",
        "user_id": "user_1",
        "session_id": session_id,
    })
    assert resp2.status_code == 200
    assert resp2.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_chat_invalid_session_returns_404(client):
    """Passing a nonexistent session_id should return 404."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
        "session_id": "nonexistent-id",
    })
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found"


@pytest.mark.asyncio
async def test_chat_stores_messages(client):
    """Chat should persist both user and assistant messages."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    messages = msgs_resp.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_chat_workflow_trigger(client):
    """Sending a workflow-suggestion message should return a workflow response."""
    resp = await client.post("/api/chat", json={
        "message": "Run MOOSE",
        "user_id": "user_1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "workflow"
    assert data["workflow_id"] is not None
    assert data["workflow_type"] == "research_and_report"
    assert data["status"] == "queued"
    assert data["session_id"] is not None


@pytest.mark.asyncio
async def test_chat_workflow_creates_step(client):
    """A workflow trigger should also create a workflow step record."""
    resp = await client.post("/api/chat", json={
        "message": "Run MOOSE",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    steps_resp = await client.get(f"/api/sessions/{session_id}/workflow-steps")
    steps = steps_resp.json()
    assert len(steps) == 1
    assert steps[0]["step_name"] == "workflow_triggered"
    assert steps[0]["step_type"] == "research_and_report"
    assert steps[0]["status"] == "pending"
    assert steps[0]["input_data"] == {"message": "Run MOOSE"}


@pytest.mark.asyncio
async def test_chat_stores_metadata(client):
    """Context and files should be stored as message metadata."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
        "context": {"key": "value"},
        "files": ["file1.txt"],
    })
    session_id = resp.json()["session_id"]

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    user_msg = msgs_resp.json()[0]
    assert user_msg["metadata"]["context"] == {"key": "value"}
    assert user_msg["metadata"]["files"] == ["file1.txt"]


@pytest.mark.asyncio
async def test_chat_no_metadata_when_empty(client):
    """When context and files are empty, metadata should be null."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
        "user_id": "user_1",
    })
    session_id = resp.json()["session_id"]

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    user_msg = msgs_resp.json()[0]
    assert user_msg["metadata"] is None


@pytest.mark.asyncio
async def test_chat_multiple_messages_accumulate(client):
    """Multiple messages in a session should all be stored in order."""
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
    await client.post("/api/chat", json={
        "message": "third",
        "user_id": "user_1",
        "session_id": session_id,
    })

    msgs_resp = await client.get(f"/api/sessions/{session_id}/messages")
    messages = msgs_resp.json()
    # 3 user messages + 3 assistant messages = 6
    assert len(messages) == 6
    user_contents = [m["content"] for m in messages if m["role"] == "user"]
    assert user_contents == ["first", "second", "third"]
