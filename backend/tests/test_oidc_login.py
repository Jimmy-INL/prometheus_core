"""Full OIDC authorization-code flow through the actual routes:
GET /api/auth/providers, GET /api/auth/login/{id}, GET /api/auth/callback/{id}.

app.oidc.fetch_discovery / exchange_code are monkeypatched to canned data (no
real network) -- the point of *this* file is the routing/cookie/session
plumbing (state+nonce round-trip, flow-cookie handling, session issuance,
users-table upsert), not HTTP mechanics (covered by test_oidc.py). ID-token
*verification* runs for real (jwt.PyJWKClient stubbed to hand back a real
locally-generated RSA public key, matching test_oidc.py's technique) so a
tampered/mismatched token is provably rejected by this same route path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from app import oidc


@pytest.fixture(scope="module")
def idp_keypair() -> tuple[str, str]:
    from prometheus_api.agent.identity_keygen import generate_keypair

    return generate_keypair(key_size=2048)


DISCOVERY = {
    "issuer": "https://idp.example.com",
    "authorization_endpoint": "https://idp.example.com/auth",
    "token_endpoint": "https://idp.example.com/token",
    "jwks_uri": "https://idp.example.com/jwks",
}


class _FakeSigningKey:
    def __init__(self, key: str) -> None:
        self.key = key


class _FakeJWKClient:
    def __init__(self, jwks_uri: str, public_key_pem: str) -> None:
        self._public_key_pem = public_key_pem

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(self._public_key_pem)


def _client(monkeypatch, *, idp_public_pem: str | None = None) -> TestClient:
    from app import security
    from app.main import app
    from app.sessions import SessionStore

    monkeypatch.setattr(security.settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(security.settings, "debug", True, raising=False)  # cookies replay over http in TestClient
    monkeypatch.setattr(oidc, "fetch_discovery", _fake_fetch_discovery)
    if idp_public_pem is not None:
        monkeypatch.setattr(oidc, "PyJWKClient", lambda jwks_uri: _FakeJWKClient(jwks_uri, idp_public_pem))
    app.state.session_store = SessionStore()
    return TestClient(app)


async def _fake_fetch_discovery(issuer_url: str) -> dict:
    return DISCOVERY


async def _register_provider(wire_db_session, **overrides) -> str:
    """Create + register an enabled OIDC provider row; returns its provider_id."""
    from app import security
    from app.crypto import encrypt
    from app.db.models import OidcProvider

    defaults = dict(
        provider_id="okta",
        display_name="Okta",
        issuer_url="https://idp.example.com",
        client_id="test-client-id",
        client_secret_encrypted=encrypt("test-client-secret"),
        scopes="openid profile email",
        default_role="user",
        is_enabled=True,
    )
    defaults.update(overrides)
    row = OidcProvider(**defaults)
    wire_db_session.add(row)
    await wire_db_session.commit()
    security.register_provider(security.GenericOidcProvider(row.provider_id))
    return row.provider_id


def _start_login(client: TestClient, provider_id: str) -> tuple[str, str, str]:
    """Hit /login/{id}; returns (state, nonce, redirect_location)."""
    resp = client.get(f"/api/auth/login/{provider_id}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    query = parse_qs(urlparse(location).query)
    return query["state"][0], query["nonce"][0], location


def _sign_id_token(private_pem: str, *, nonce: str, sub: str = "user-123", **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://idp.example.com",
        "sub": sub,
        "aud": "test-client-id",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "nonce": nonce,
        "email": "alice@example.com",
        "preferred_username": "alice",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


# --------------------------------------------------------------------------- #
# GET /api/auth/providers
# --------------------------------------------------------------------------- #


async def test_providers_lists_only_enabled(monkeypatch, wire_db_session):
    await _register_provider(wire_db_session, provider_id="enabled-one", display_name="Enabled One")
    await _register_provider(wire_db_session, provider_id="disabled-one", display_name="Disabled One", is_enabled=False)
    client = _client(monkeypatch)

    resp = client.get("/api/auth/providers")
    assert resp.status_code == 200
    ids = {p["provider_id"] for p in resp.json()}
    assert ids == {"enabled-one"}


# --------------------------------------------------------------------------- #
# GET /api/auth/login/{provider_id}
# --------------------------------------------------------------------------- #


def test_login_unknown_provider_404s(monkeypatch, wire_db_session):
    client = _client(monkeypatch)
    assert client.get("/api/auth/login/nope", follow_redirects=False).status_code == 404


async def test_login_redirects_with_state_and_nonce_and_sets_flow_cookie(monkeypatch, wire_db_session):
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch)

    resp = client.get(f"/api/auth/login/{provider_id}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://idp.example.com/auth?")
    query = parse_qs(urlparse(location).query)
    assert query["client_id"][0] == "test-client-id"
    assert query["response_type"][0] == "code"
    assert "state" in query and "nonce" in query
    assert resp.cookies.get("oidc_flow")


async def test_login_404s_for_a_disabled_provider(monkeypatch, wire_db_session):
    provider_id = await _register_provider(wire_db_session, is_enabled=False)
    client = _client(monkeypatch)
    assert client.get(f"/api/auth/login/{provider_id}", follow_redirects=False).status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/auth/callback/{provider} -- happy path
# --------------------------------------------------------------------------- #


async def test_full_login_round_trip_creates_user_and_session(monkeypatch, wire_db_session, idp_keypair):
    private_pem, public_pem = idp_keypair
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch, idp_public_pem=public_pem)

    state, nonce, _ = _start_login(client, provider_id)

    async def _exchange(discovery, provider, *, code, redirect_uri):
        assert code == "the-auth-code"
        return {"id_token": _sign_id_token(private_pem, nonce=nonce)}

    monkeypatch.setattr(oidc, "exchange_code", _exchange)

    resp = client.get(
        f"/api/auth/callback/{provider_id}", params={"code": "the-auth-code", "state": state}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert resp.cookies.get("prometheus_session")
    # The flow cookie is cleared once the handshake completes.
    assert "oidc_flow=" not in resp.headers.get("set-cookie", "") or 'oidc_flow=""' in resp.headers.get(
        "set-cookie", ""
    )

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["identifier"] == "alice"  # from preferred_username
    assert body["role"] == "user"
    assert body["provider"] == provider_id


async def test_second_login_reuses_the_same_account(monkeypatch, wire_db_session, idp_keypair):
    from sqlalchemy import select

    from app.db.models import User as UserRow

    private_pem, public_pem = idp_keypair
    provider_id = await _register_provider(wire_db_session)

    for _ in range(2):
        client = _client(monkeypatch, idp_public_pem=public_pem)
        state, nonce, _ = _start_login(client, provider_id)

        async def _exchange(discovery, provider, *, code, redirect_uri, _nonce=nonce):
            return {"id_token": _sign_id_token(private_pem, nonce=_nonce)}

        monkeypatch.setattr(oidc, "exchange_code", _exchange)
        client.get(f"/api/auth/callback/{provider_id}", params={"code": "c", "state": state}, follow_redirects=False)

    rows = (await wire_db_session.scalars(select(UserRow).where(UserRow.provider == provider_id))).all()
    assert len(rows) == 1  # not duplicated on the second login


# --------------------------------------------------------------------------- #
# GET /api/auth/callback/{provider} -- failure paths
# --------------------------------------------------------------------------- #


def test_callback_unknown_provider_returns_501(monkeypatch, wire_db_session):
    client = _client(monkeypatch)
    resp = client.get("/api/auth/callback/nope", params={"code": "x", "state": "y"})
    assert resp.status_code == 501


async def test_callback_without_flow_cookie_400s(monkeypatch, wire_db_session):
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch)
    resp = client.get(f"/api/auth/callback/{provider_id}", params={"code": "x", "state": "y"})
    assert resp.status_code == 400


async def test_callback_with_wrong_state_400s(monkeypatch, wire_db_session, idp_keypair):
    _, public_pem = idp_keypair
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch, idp_public_pem=public_pem)
    _, _, _ = _start_login(client, provider_id)

    resp = client.get(f"/api/auth/callback/{provider_id}", params={"code": "x", "state": "not-the-real-state"})
    assert resp.status_code == 400


async def test_callback_surfaces_idp_error_param(monkeypatch, wire_db_session):
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch)
    _start_login(client, provider_id)

    resp = client.get(f"/api/auth/callback/{provider_id}", params={"error": "access_denied"})
    assert resp.status_code == 400


async def test_callback_rejects_tampered_id_token(monkeypatch, wire_db_session, idp_keypair):
    """The JWKS reports a different key than what actually signed the token --
    proves signature verification runs for real through this route, not just
    in test_oidc.py's direct unit tests."""
    from prometheus_api.agent.identity_keygen import generate_keypair

    private_pem, _ = idp_keypair
    _, attacker_public_pem = generate_keypair(key_size=2048)
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch, idp_public_pem=attacker_public_pem)
    state, nonce, _ = _start_login(client, provider_id)

    async def _exchange(discovery, provider, *, code, redirect_uri):
        return {"id_token": _sign_id_token(private_pem, nonce=nonce)}

    monkeypatch.setattr(oidc, "exchange_code", _exchange)
    resp = client.get(f"/api/auth/callback/{provider_id}", params={"code": "c", "state": state})
    assert resp.status_code == 400


async def test_callback_rejects_deactivated_account(monkeypatch, wire_db_session, idp_keypair):
    from sqlalchemy import select

    from app.db.models import User as UserRow

    private_pem, public_pem = idp_keypair
    provider_id = await _register_provider(wire_db_session)
    client = _client(monkeypatch, idp_public_pem=public_pem)
    state, nonce, _ = _start_login(client, provider_id)

    async def _exchange(discovery, provider, *, code, redirect_uri):
        return {"id_token": _sign_id_token(private_pem, nonce=nonce, sub="deactivated-user")}

    monkeypatch.setattr(oidc, "exchange_code", _exchange)
    resp = client.get(f"/api/auth/callback/{provider_id}", params={"code": "c", "state": state}, follow_redirects=False)
    assert resp.status_code in (302, 307)  # first login succeeds, creating the account

    row = await wire_db_session.scalar(select(UserRow).where(UserRow.external_subject == "deactivated-user"))
    row.is_active = False
    await wire_db_session.commit()

    # Second attempt, same identity, now deactivated.
    client2 = _client(monkeypatch, idp_public_pem=public_pem)
    state2, nonce2, _ = _start_login(client2, provider_id)

    async def _exchange2(discovery, provider, *, code, redirect_uri):
        return {"id_token": _sign_id_token(private_pem, nonce=nonce2, sub="deactivated-user")}

    monkeypatch.setattr(oidc, "exchange_code", _exchange2)
    resp2 = client2.get(f"/api/auth/callback/{provider_id}", params={"code": "c", "state": state2})
    assert resp2.status_code == 400
