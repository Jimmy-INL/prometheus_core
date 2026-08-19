"""Auth + hardening tests (remediation step 05).

Covers logout revocation (AU-1), constant-time password check (AU-3), the
authenticated ``/api/config`` (AU-5), the identity-provider registry / OAuth seam
(AU-6), and the non-wildcard dev CORS origins (AU-9).
"""

from fastapi.testclient import TestClient


def _authed(monkeypatch, *, sid: str) -> tuple[TestClient, object]:
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
    return client, settings


# --------------------------------------------------------------------------- #
# AU-1 — logout invalidates the JWT (not just the cookie)
# --------------------------------------------------------------------------- #


def test_logout_revokes_token_even_if_replayed(monkeypatch):
    client, settings = _authed(monkeypatch, sid="sid-logout-unique")
    token = client.cookies.get(settings.cookie_name)
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200

    # Replay the *same* token (delete_cookie only clears the browser copy). Revocation
    # must reject it, proving logout isn't merely client-side.
    client.cookies.set(settings.cookie_name, token)
    assert client.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# AU-3 — password check: correctness + constant-time compare
# --------------------------------------------------------------------------- #


def test_password_provider_authenticates_and_rejects(monkeypatch):
    from app import security
    from app.config import settings

    monkeypatch.setattr(
        settings, "local_users", [{"username": "u", "password": "s3cret", "role": "admin"}], raising=False
    )
    provider = security.PasswordIdentityProvider()
    ok = provider.authenticate("u", "s3cret")
    assert ok is not None and ok.role == "admin"
    assert provider.authenticate("u", "wrong") is None  # wrong password
    assert provider.authenticate("nope", "s3cret") is None  # unknown user
    assert provider.authenticate("u", "") is None  # empty password never matches


# --------------------------------------------------------------------------- #
# AU-5 — /api/config is authenticated
# --------------------------------------------------------------------------- #


def test_config_requires_auth():
    from app.main import app
    from app.sessions import SessionStore

    app.state.session_store = SessionStore()
    assert TestClient(app).get("/api/config").status_code == 401


def test_config_returns_settings_when_authed(monkeypatch):
    client, _ = _authed(monkeypatch, sid="sid-config")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert "max_upload_bytes" in resp.json()


# --------------------------------------------------------------------------- #
# AU-6 — identity-provider registry / OAuth seam
# --------------------------------------------------------------------------- #


def test_provider_registry_resolves_credentials(monkeypatch):
    from app import security

    assert security.get_provider("credentials") is security.password_provider
    assert security.get_provider("does-not-exist") is None


def test_oauth_callback_not_implemented(monkeypatch):
    client, _ = _authed(monkeypatch, sid="sid-oauth")
    assert client.get("/api/auth/callback/okta").status_code == 501


# --------------------------------------------------------------------------- #
# AU-9 — dev CORS origins are explicit, never a credentialed wildcard
# --------------------------------------------------------------------------- #


def test_dev_cors_origins_are_explicit():
    from app.config import settings

    assert "*" not in settings.dev_cors_origins
    assert settings.dev_cors_origins  # non-empty
    assert all(o.startswith("http") for o in settings.dev_cors_origins)
