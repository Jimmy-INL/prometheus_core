"""POST /api/sessions tests — profile validation (remediation step 05, AU-8)."""

from fastapi.testclient import TestClient


def _authed(monkeypatch, *, sid: str = "sid-session") -> TestClient:
    from app import security
    from app.config import settings
    from app.main import app
    from app.sessions import SessionStore

    monkeypatch.setattr(settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(security.settings, "jwt_secret", "test-secret", raising=False)

    store = SessionStore()
    store.get_or_create(sid)
    app.state.session_store = store
    token = security.issue_token(security.User(identifier="alice"), sid=sid)
    client = TestClient(app)
    client.cookies.set(settings.cookie_name, token)
    return client


def test_create_session_defaults_to_beginner(monkeypatch):
    client = _authed(monkeypatch)
    resp = client.post("/api/sessions", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] == "Beginner Chat"
    assert body["conversation_id"]
    assert body["workflow_suggestions"]  # beginner carries suggestions


def test_create_session_accepts_valid_profile(monkeypatch):
    client = _authed(monkeypatch)
    resp = client.post("/api/sessions", json={"profile": "Advanced Chat"})
    assert resp.status_code == 200
    assert resp.json()["profile"] == "Advanced Chat"
    assert resp.json()["workflow_suggestions"] == []  # advanced: no suggestions


def test_create_session_rejects_unknown_profile(monkeypatch):
    client = _authed(monkeypatch)
    resp = client.post("/api/sessions", json={"profile": "Bogus Profile"})
    assert resp.status_code == 422
