from unittest.mock import patch, MagicMock

import pytest


WORKFLOW_PROMPT = (
    "Design a Rankine cycle based power generation system for a Sodium Fast Reactor."
    " Core power rating is 390 MW, turbine output is 170.9 MW"
)


# -- Workflow trigger tests --


@pytest.mark.asyncio
async def test_chat_workflow_trigger(client):
    """Sending a recognised workflow prompt should return a workflow response."""
    resp = await client.post("/api/chat", json={
        "message": WORKFLOW_PROMPT,
        "user_id": "user_1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "workflow"
    assert data["workflow_id"] is not None
    assert data["workflow_type"] == "research_and_report"
    assert data["status"] == "queued"
    assert data["session_id"] == "tmp"


@pytest.mark.asyncio
async def test_chat_ftl_workflow_trigger(client):
    """The FTL safety analysis prompt should also trigger a workflow."""
    resp = await client.post("/api/chat", json={
        "message": "Run FTL Safety Analysis",
        "user_id": "user_1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "workflow"
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_chat_fmea_trigger(client):
    """Sending 'fmea' should trigger the FMEA workflow."""
    resp = await client.post("/api/chat", json={
        "message": "fmea",
        "user_id": "user_1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "fmea_workflow"
    assert data["workflow_id"] == "wf_fmea"
    assert data["status"] == "queued"


# -- LLM chat tests (mocked) --


@pytest.mark.asyncio
async def test_chat_llm_response(client):
    """Non-workflow messages should be forwarded to the LLM and return a chat response."""
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello! I'm Prometheus."
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("routers.chat.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value.chat.completions.create.return_value = mock_completion
        resp = await client.post("/api/chat", json={
            "message": "hello",
            "user_id": "user_1",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "chat"
    assert data["response"] == "Hello! I'm Prometheus."
    assert data["session_id"] == "tmp"


@pytest.mark.asyncio
async def test_chat_llm_failure_returns_fallback(client):
    """When the LLM call fails, the endpoint should return a graceful fallback message."""
    with patch("routers.chat.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value.chat.completions.create.side_effect = Exception("connection error")
        resp = await client.post("/api/chat", json={
            "message": "hello",
            "user_id": "user_1",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "chat"
    assert "unable to process" in data["response"].lower()


# -- Request validation --


@pytest.mark.asyncio
async def test_chat_missing_message_returns_422(client):
    """Omitting the required 'message' field should return a validation error."""
    resp = await client.post("/api/chat", json={
        "user_id": "user_1",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_user_id_returns_422(client):
    """Omitting the required 'user_id' field should return a validation error."""
    resp = await client.post("/api/chat", json={
        "message": "hello",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_workflow_response_has_polling_url(client):
    """Workflow responses should include a polling URL."""
    resp = await client.post("/api/chat", json={
        "message": WORKFLOW_PROMPT,
        "user_id": "user_1",
    })
    data = resp.json()
    assert data["polling_url"] is not None
    assert "workflows" in data["polling_url"]
