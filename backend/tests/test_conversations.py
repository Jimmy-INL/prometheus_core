"""Offline tests for GET /api/conversations/recent (task 08).

Drive the endpoint against a ``TestClient`` with ``ConversationStateClient``
replaced by an in-memory fake — no live Redis. Covers the Redis-down graceful
degrade, populated results, auth, and limit validation. The 200 cases also prove
the router is mounted in ``app/main.py``.
"""

from fastapi.testclient import TestClient

from app.routers import conversations as conversations_router


class _FakeClient:
    """Stand-in for ConversationStateClient with canned availability + rows."""

    def __init__(self, *, available: bool, rows: list[dict]):
        self._available = available
        self._rows = rows
        self.last_limit: int | None = None
        self.last_user_id: str | None = None

    @property
    def available(self) -> bool:
        return self._available

    def get_conversation_history(self, limit: int = 20, user_id: str | None = None) -> list[dict]:
        self.last_limit = limit
        self.last_user_id = user_id
        return self._rows[:limit]


def _patch_client(monkeypatch, *, available: bool, rows: list[dict]) -> _FakeClient:
    fake = _FakeClient(available=available, rows=rows)
    monkeypatch.setattr(conversations_router, "ConversationStateClient", lambda _url: fake)
    return fake


def _authed_client(monkeypatch) -> TestClient:
    from app import security
    from app.config import settings
    from app.main import app
    from app.sessions import SessionStore

    monkeypatch.setattr(settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(security.settings, "jwt_secret", "test-secret", raising=False)

    app.state.session_store = SessionStore()
    token = security.issue_token(security.User(identifier="alice"), sid="sid-conv")
    client = TestClient(app)
    client.cookies.set(settings.cookie_name, token)
    return client


def test_recent_requires_auth():
    from app.main import app
    from app.sessions import SessionStore

    app.state.session_store = SessionStore()
    client = TestClient(app)
    resp = client.get("/api/conversations/recent")
    assert resp.status_code == 401


def test_recent_degrades_gracefully_when_redis_down(monkeypatch):
    _patch_client(monkeypatch, available=False, rows=[])
    client = _authed_client(monkeypatch)

    resp = client.get("/api/conversations/recent")
    assert resp.status_code == 200
    assert resp.json() == {"available": False, "conversations": []}


def test_recent_returns_conversations(monkeypatch):
    rows = [
        {
            "conversation_id": "c2",
            "query": "corrosion rate?",
            "status": "completed",
            "material_id": "SS316",
            "timestamp": "2026-08-11T10:00:00Z",
        },
        {
            "conversation_id": "c1",
            "query": "hello",
            "status": "unknown",
            "material_id": None,
            "timestamp": "2026-08-10T09:00:00Z",
        },
    ]
    _patch_client(monkeypatch, available=True, rows=rows)
    client = _authed_client(monkeypatch)

    resp = client.get("/api/conversations/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert [c["conversation_id"] for c in body["conversations"]] == ["c2", "c1"]
    assert body["conversations"][0]["material_id"] == "SS316"
    assert body["conversations"][1]["material_id"] is None


def test_recent_scopes_by_authenticated_user(monkeypatch):
    """GET /api/conversations/recent must pass the caller's own user_id, not
    some other user's -- this is the fix for the pre-multi-user global scan."""
    fake = _patch_client(monkeypatch, available=True, rows=[])
    client = _authed_client(monkeypatch)  # issues a token for identifier="alice"

    resp = client.get("/api/conversations/recent")
    assert resp.status_code == 200
    assert fake.last_user_id == "alice"


def test_recent_forwards_limit(monkeypatch):
    fake = _patch_client(monkeypatch, available=True, rows=[])
    client = _authed_client(monkeypatch)

    resp = client.get("/api/conversations/recent?limit=5")
    assert resp.status_code == 200
    assert fake.last_limit == 5


def test_recent_rejects_out_of_range_limit(monkeypatch):
    _patch_client(monkeypatch, available=True, rows=[])
    client = _authed_client(monkeypatch)

    assert client.get("/api/conversations/recent?limit=0").status_code == 422
    assert client.get("/api/conversations/recent?limit=1000").status_code == 422


# --------------------------------------------------------------------------- #
# AU-2 — ConversationStateClient sorts before slicing (returns the newest)
# --------------------------------------------------------------------------- #


def test_get_history_sorts_before_slicing(monkeypatch):
    """With more conversations than the limit, the newest are returned — not an
    arbitrary unordered subset (the old slice-before-sort bug)."""
    import json as _json

    from app.conversation_state import ConversationStateClient

    # keys() returns them oldest-first; a slice-before-sort with limit=2 would keep
    # {old, mid} and drop the newest. Sort-before-slice must return {new, mid}.
    blobs = {
        "conversation:old": {"user_query": "old", "conversation_history": [{"timestamp": "2026-01-01T00:00:00Z"}]},
        "conversation:mid": {"user_query": "mid", "conversation_history": [{"timestamp": "2026-05-01T00:00:00Z"}]},
        "conversation:new": {"user_query": "new", "conversation_history": [{"timestamp": "2026-08-01T00:00:00Z"}]},
    }

    class _FakeRedis:
        def keys(self, pattern):
            return list(blobs.keys())

        def get(self, key):
            return _json.dumps(blobs[key])

    c = ConversationStateClient("redis://x")
    monkeypatch.setattr(type(c), "client", property(lambda self: _FakeRedis()))

    rows = c.get_conversation_history(limit=2)
    assert [r["conversation_id"] for r in rows] == ["new", "mid"]


# --------------------------------------------------------------------------- #
# Per-user history scoping (user:convs:{user_id} index, not a global scan)
# --------------------------------------------------------------------------- #


def test_get_history_scopes_to_user_id_via_index(monkeypatch):
    """With user_id set, only conversations in that user's index are read --
    conversations belonging to other users must never be scanned or returned."""
    import json as _json

    from app.conversation_state import ConversationStateClient

    blobs = {
        "conversation:mine": {"user_query": "mine", "conversation_history": [{"timestamp": "2026-08-01T00:00:00Z"}]},
        "conversation:theirs": {
            "user_query": "theirs",
            "conversation_history": [{"timestamp": "2026-08-02T00:00:00Z"}],
        },
    }

    class _FakeRedis:
        def keys(self, pattern):  # must NOT be called on the scoped path
            raise AssertionError("global keys() scan used despite user_id being provided")

        def smembers(self, key):
            assert key == "user:convs:alice"
            return {"mine"}

        def get(self, key):
            return _json.dumps(blobs[key])

    c = ConversationStateClient("redis://x")
    monkeypatch.setattr(type(c), "client", property(lambda self: _FakeRedis()))

    rows = c.get_conversation_history(limit=20, user_id="alice")
    assert [r["conversation_id"] for r in rows] == ["mine"]


def test_get_history_falls_back_to_global_scan_without_user_id(monkeypatch):
    """user_id=None preserves the legacy global scan (pre-ownership-tracking data)."""
    import json as _json

    from app.conversation_state import ConversationStateClient

    blobs = {
        "conversation:a": {"user_query": "a", "conversation_history": [{"timestamp": "2026-08-01T00:00:00Z"}]},
    }

    class _FakeRedis:
        def keys(self, pattern):
            assert pattern == "conversation:*"
            return list(blobs.keys())

        def get(self, key):
            return _json.dumps(blobs[key])

    c = ConversationStateClient("redis://x")
    monkeypatch.setattr(type(c), "client", property(lambda self: _FakeRedis()))

    rows = c.get_conversation_history(limit=20)
    assert [r["conversation_id"] for r in rows] == ["a"]
