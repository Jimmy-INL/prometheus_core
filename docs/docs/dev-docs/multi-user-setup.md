# Multi-User Setup

This document covers how to configure and operate the Prometheus platform for
multiple simultaneous users.  It is the operator/developer companion to the
`prometheus_api` implementation reference at
`prometheus_api/docs/agent/MULTI_USER.md`.

---

## How multi-user works at the platform level

The frontend is a React SPA (`frontend/`) talking to a standalone FastAPI
`backend/` service (`app/routers/*`, `app/services/*`) — the successor to the
old Chainlit Python frontend. Login, session state, and A2A calls all live in
`backend/`; the identity plane sits on top of that:

```
User logs in (local password today; OAuth is a modeled-but-deferred seam)
    ↓
backend/app/security.py issues a session-cookie JWT (BACKEND_JWT_SECRET),
carrying { sub: user_id, role, sid, exp } — this is NOT the identity token below
    ↓
Every POST /api/chat/messages (backend/app/routers/chat.py):
  identity.mint_for_user(claims.sub) mints a short-lived PLATFORM JWT
  (USER_IDENTITY_SECRET) via prometheus_api.agent.identity.mint_user_token
    ↓
backend/app/a2a_client.py::A2AClient.send() attaches it to
  message.metadata["userToken"] on the outbound A2A call
    ↓
client-agent verifies the JWT → establishes identity_scope for the turn
  ├─ Binds conversation_id to user_id on first touch (conv_owner Redis key)
  ├─ Rejects cross-user access to existing conversations
  └─ Propagates userToken to every downstream specialist agent call
    ↓
Specialist agents verify the JWT independently
  └─ Can call self.get_credential(resource) for per-user JIT secrets
```

**Two distinct JWTs, two distinct secrets** — easy to conflate, so be precise:
- `BACKEND_JWT_SECRET` (or its `CHAINLIT_AUTH_SECRET` fallback) signs the
  **browser session cookie** — backend-to-browser only, never leaves the backend.
- `USER_IDENTITY_SECRET` (or an RS256 keypair) signs the **platform identity
  JWT** — backend-to-agents, carried in `message.metadata["userToken"]`.

The platform mints its **own** internal identity JWT rather than forwarding the
session cookie or any external IdP token. This means multi-user works
correctly even when deployed without a federated IdP (e.g. local password
users only).

---

## Configuration

### Required env vars (add to `.env`)

```bash
# Identity — must match across all services (backend + all agents)
USER_IDENTITY_SECRET=change-this-to-a-long-random-string
USER_IDENTITY_ALG=HS256          # HS256 (default) or RS256
USER_IDENTITY_ISS=prometheus-platform   # default
USER_IDENTITY_AUD=prometheus-agents     # default
USER_IDENTITY_TTL=7200           # seconds; must cover the longest expected turn
USER_IDENTITY_REQUIRED=true      # false for dev/smoke-test only
```

For RS256 (asymmetric, preferred for production):
```bash
USER_IDENTITY_ALG=RS256
USER_IDENTITY_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
USER_IDENTITY_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n..."
# Private key is only needed by the backend (minting).
# Public key is sufficient for agents (verification only).
```

### `.env.example` additions (already added)

The following variables have been added to `docker-compose.yml` and should be
templated in `.env.example`:
```
USER_IDENTITY_SECRET=
USER_IDENTITY_REQUIRED=true
CREDENTIAL_BROKER=env
```

### Local users

Add users in `backend/app/config.yml`:
```yaml
local-users:
  - username: "alice"
    password: "replace-with-a-strong-password"
    role: "admin"
  - username: "bob"
    password: "replace-with-another-strong-password"
    role: "user"
```

Plain-text passwords are dev-only (`backend/app/security.py::PasswordIdentityProvider`
compares with `hmac.compare_digest`; hashed-at-rest storage is a deferred follow-up).

**Okta/OIDC is not wired up yet.** `security.py` models an `IdentityProvider`
protocol with a provider registry (`register_provider()`/`get_provider()`) so a
real OAuth provider is a drop-in later, but only the password provider is
registered today — `GET /api/auth/callback/{provider}` stubs `501` regardless
of which `.env` `OAUTH_OKTA_*` vars are set. Whichever identity source ends up
wired through this seam, the identity-plane code in this doc is unaffected:
`identity.mint_for_user(claims.sub)` mints from whatever `sub` the login flow
resolves, local password or OIDC alike.

---

## Credential broker

### Development (default)

No extra config needed.  Set `CREDENTIAL_BROKER=env` (or omit it — it is the
default) and configure the global credentials as before:
```bash
CREDENTIAL_BROKER=env
DEEPLYNX_JWT_TOKEN=...
DEEPLYNX_ORG_ID=42
DEEPLYNX_PROJECT_ID=7
SLURM_JWT_TOKEN=...
SLURM_REST_URL=http://slurm.hpc/slurm/v0.0.40
```
All users receive the same global credentials.  Appropriate for dev, CI, and
single-user deployments.

### Production with Vault

```bash
CREDENTIAL_BROKER=vault
VAULT_ADDR=https://vault.example.com
VAULT_JWT_ROLE=prometheus-agent
# One of the following workload auth methods:
VAULT_AGENT_SECRET=<per-agent-shared-secret>
# or mTLS (stronger):
VAULT_MTLS_CERT=/certs/agent.crt
VAULT_MTLS_KEY=/certs/agent.key
VAULT_MTLS_CA=/certs/ca.crt
```

Each user must link their resource credentials once (via a forthcoming
consent UI or directly in Vault) at the paths the policy covers:
```
secret/data/deeplynx/{user_id}   →  {"jwt_token": "user-specific-dl-token"}
secret/data/slurm/{user_id}      →  {"token": "user-slurm-token", "user": "hpcuser"}
```

See `prometheus_api/docs/agent/MULTI_USER.md` § Vault broker for the full Vault
policy HCL.

### Third-party agent providers

If an external team or vendor registers an agent with your platform, **use RS256**.
Give them only the `USER_IDENTITY_PUBLIC_KEY` — they can verify that incoming JWTs
were signed by your platform without being able to forge tokens.

With HS256 you would have to share `USER_IDENTITY_SECRET`, which lets them
impersonate any user.  Never do this.

Every `PrometheusAgent` now serves `GET /.well-known/jwks.json` — the RSA public
key as a JSON Web Key Set.  Third-party agents set `JWKS_URL` to this endpoint
and `verify_user_token` fetches and caches the key automatically, with transparent
key rotation via the JWT `kid` header.  No private key or shared secret needs to
leave your organisation.

See `prometheus_api/docs/agent/IDENTITY_KEY_MANAGEMENT.md` for the full key
distribution table, key generation steps, and rotation guide.

---

## Mesh/IFC dataset isolation (decision: no per-user path namespacing)

`GET /api/artifacts/mesh/{dataset_id}/{filename}` (`backend/app/routers/artifacts.py`)
requires a valid session (`Depends(current_claims)`) — a real improvement over
the old Chainlit setup, which served `/public/mesh-data/{dataset_id}/...`
**unauthenticated**. But the endpoint is deliberately **not** per-user
path-namespaced: `dataset_id` is a content hash and the converted-VTP cache is
shared across users by design (uploading the same file twice converts once).

This is intentional, not an oversight. The actual data-access boundary is
**DeepLynx itself**: each user/project has separate DeepLynx credentials
(see Credential broker below), so a user can never reach another user's
*source* artifact regardless of how the local rendering cache is laid out —
namespacing the local VTP cache by user would only protect a cache of content
the requester could already fetch on their own. `GET /api/artifacts/{id}/content`
(the non-mesh artifact endpoint) is separately — and more strongly — isolated:
it resolves against `session.artifacts`, so it can only ever address the
calling session's own catalog.

If this changes (e.g. mesh conversion moves to per-user DeepLynx-backed
storage rather than a local disk cache), revisit this section before assuming
the auth gate alone is sufficient.

---

## Conversation isolation

Each conversation is owned by the user who created it:

- **First turn**: `record_conversation_owner(conv_id, user_id)` writes a Redis
  key `conv_owner:{conv_id} = user_id` and adds `conv_id` to
  `user:convs:{user_id}`.
- **Subsequent turns**: `assert_conversation_owner(conv_id, user_id)` rejects the
  request if a different user owns it.
- **`/history`**: scoped to the current user via the `user:convs:{user_id}` Redis
  set — no global scan.

The underlying Redis keys for artifacts, task graphs, and status are **not**
renamed; access control is enforced at the entry point only.  This is correct
because `conversation_id` is a random UUID that is unguessable in practice.

---

## User-scoped uploads

`POST /api/uploads` (`backend/app/routers/uploads.py`) mints a `user_token` via
`identity.mint_for_user(claims.sub)` and passes it to
`A2AClient.stage_upload(..., user_token=...)`, which forwards it as an explicit
**query param** on the client-agent's raw `/uploads/stage` endpoint
(`agents/client-agent/orchestrator/service.py::_stage_upload_endpoint`).

That endpoint verifies the token directly (`verify_user_token(user_token)`)
rather than reading the ambient identity context — it's a raw Starlette route
added via `app.add_route`, not routed through `PrometheusAgentExecutor.execute()`,
so no `identity_scope()` is ever active there. (An earlier version of this code
tried to read `current_user_id()` from that ambient context and always got
`None` — a real bug, not a hypothetical; if you see staged uploads with an
empty `user_id`, check that `user_token` is actually being passed as a query
param, not assumed from context.)

The verified `user_id` is stamped into the staged upload's metadata. When the
agent later processes the upload, it rejects retrieval by a different user:

```python
# file_upload_handler.resolve_staged_upload(uploaded_file, user_id="alice")
# → raises PermissionError if the upload was staged by "bob"
```

---

## Developer guide: adding credentials to a new agent

1. Set `requires_user_isolation = True` on the agent if it holds credentials
   across multiple `await` calls (e.g. job submission + polling).  Stateless
   agents that fetch and immediately use a credential do not need it.

2. Call `self.get_credential(resource)` inside `_execute`:

```python
from prometheus_api.agent import PrometheusAgent
from prometheus_api.storage_client.connection import ConnectionConfig

class MyNewAgent(PrometheusAgent):
    requires_user_isolation = True   # optional; set if holding creds across awaits

    async def _execute(self, params, context, event_queue):
        user_id = params["user_id"]   # already verified

        # JIT credential — never cache this
        cred = await self.get_credential("deeplynx")
        config = ConnectionConfig.from_credential(cred)

        await self.send_status_update(context, event_queue,
            message=f"Fetching data for {user_id}...")
        # ... use config ...
        return {"status": "success"}
```

3. Add the agent's resource requirements to its `agent_card.json` (future:
   will feed the consent/permission UI):

```json
{
  "name": "my-new-agent",
  "required_credentials": [
    {"resource": "deeplynx", "required": true}
  ]
}
```

4. Run `make generate` to pick up the new `docker-compose.yml` if you created a
   new agent directory.

---

## Running without multi-user (single-user / dev)

Set `USER_IDENTITY_REQUIRED=false` in `.env`.  Agents synthesise a synthetic
`UserIdentity(user_id="local")` for requests that carry no `userToken`.  All
existing behaviour is preserved.  The ownership and history-scoping features
still work (scoped to the `"local"` user_id).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent returns `"Identity verification failed: userToken has expired"` | Turn lasted longer than `USER_IDENTITY_TTL` | Increase `USER_IDENTITY_TTL` (default 7200) |
| Agent returns `"No 'userToken' found in message metadata"` | `USER_IDENTITY_REQUIRED=true` but `backend` has no `USER_IDENTITY_SECRET` configured | Set `USER_IDENTITY_SECRET` in `.env` |
| `CredentialError: VAULT_ADDR is required` | `CREDENTIAL_BROKER=vault` but Vault env not set | Set `VAULT_ADDR` and `VAULT_JWT_ROLE`, or switch to `CREDENTIAL_BROKER=env` |
| `/history` shows no conversations | User has not yet created any conversations in this deployment | Expected — history is now per-user |
| Worker pool capacity error | Too many concurrent users for `USER_WORKER_MAX` | Increase `USER_WORKER_MAX` (default 32) |

---

## See also

- `prometheus_api/docs/agent/MULTI_USER.md` — implementation reference for agent authors
- `prometheus_api/docs/agent/IDENTITY_KEY_MANAGEMENT.md` — HS256 vs RS256, key distribution, third-party agent integration via JWKS
- `prometheus_api/docs/agent/GUIDE.md` — general PrometheusAgent developer guide
- `docs/docs/dev-docs/adding-agents.md` — how to create a new specialist agent
- `docs/docs/dev-docs/artifacts.md` — artifact model and rendering
