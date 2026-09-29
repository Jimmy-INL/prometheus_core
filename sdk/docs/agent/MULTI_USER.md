# Multi-User Identity, Credentials, and Isolation

This document covers the three additions that make `PrometheusAgent`-based systems
safe to run with multiple concurrent users:

1. **Identity** — the platform mints a short-lived JWT for each authenticated user
   and propagates it to every agent call so that `_execute` always knows who it is
   acting for.
2. **Credentials** — a pluggable `CredentialBroker` issues per-user, per-resource,
   short-lived credentials (DeepLynx tokens, SLURM tokens) on demand.  Secrets are
   never cached past a single operation and never travel through LiteLLM.
3. **Process isolation** — credential-touching agents can opt into a per-user worker
   process so that one user's live secrets cannot leak into another's memory space.

---

## Why two planes?

Platform identity (who is the user) and downstream credential access (what external
systems may this user's agents touch) are intentionally separate:

- **Identity** is platform-internal — the platform backend mints its own JWT after
  login, regardless of whether the user authenticated via Okta, generic OIDC, or a
  local password.  Agents verify *this* token, not the external IdP token.  This
  means the platform deploys identically whether or not a federated IdP exists.
- **Credentials** are user-linked — the broker fetches JIT credentials *on behalf of*
  the verified user.  A scoping bug exposes chat data; a credentials bug exposes real
  third-party access.  The higher blast radius justifies independent hardening.

---

## 1. Identity

### How it works

```
User logs in (Okta / OIDC / local password)
    ↓
Backend mints a short-lived RS256 platform JWT, signed with USER_IDENTITY_PRIVATE_KEY
  { sub: "alice", iss: "prometheus-platform", aud: "prometheus-agents", exp: <now+2h> }
    ↓
JWT placed in A2A message.metadata["userToken"] on every turn
    ↓
PrometheusAgentExecutor.execute() calls _extract_identity(context)
  → verify_user_token(raw_token) — checks signature, exp, iss, aud
  → wraps _execute() in identity_scope(identity)
    ↓
params["user_id"] == "alice" inside _execute()
self.current_user_id() == "alice" inside _execute()
```

### Reading the current user in `_execute`

```python
from prometheus_api.agent import PrometheusAgent

class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        user_id = params["user_id"]   # verified, never spoofable
        # or equivalently:
        user_id = self.current_user_id()
        ...
```

`params["user_id"]` is injected by the base class after JWT verification.
It is never attacker-controlled.

### Propagating identity to downstream agents

When your agent calls another agent (via an internal A2A call), include the
current user token so the downstream agent can verify the same identity:

```python
metadata = self.identity_metadata()
# {"userToken": "<raw_platform_jwt>"}

# Pass metadata when building the outbound A2A message envelope.
```

The client-agent does this automatically for all specialist agent calls via
`tool_discovery.call_a2a_agent()`.

### Environment variables

Signing is **RS256 only** — there is no symmetric-secret option. Generate a keypair
with `prometheus-identity-keygen` (ships in this package) or `openssl`; see
[IDENTITY_KEY_MANAGEMENT.md](./IDENTITY_KEY_MANAGEMENT.md).

| Variable | Default | Description | Needed by |
|---|---|---|---|
| `USER_IDENTITY_PRIVATE_KEY` | *(required to mint)* | PEM private key | **Backend only** |
| `USER_IDENTITY_PUBLIC_KEY` | *(required to verify)* | PEM public key | Every agent |
| `JWKS_URL` | — | Fetch the public key remotely instead of a static value | Third-party agents |
| `USER_IDENTITY_ISS` | `prometheus-platform` | JWT issuer claim | Backend + agents |
| `USER_IDENTITY_AUD` | `prometheus-agents` | JWT audience claim | Backend + agents |
| `USER_IDENTITY_TTL` | `7200` | Token lifetime in seconds | Backend only (minting) |
| `USER_IDENTITY_REQUIRED` | `true` | Set `false` to skip verification (dev only) | Every agent |

**Which services need which key?** Only the backend needs `USER_IDENTITY_PRIVATE_KEY` —
it is the only thing that ever mints a token. Every agent, including third-party ones,
needs only `USER_IDENTITY_PUBLIC_KEY` (or `JWKS_URL`) — enough to verify, never enough
to forge. See [IDENTITY_KEY_MANAGEMENT.md](./IDENTITY_KEY_MANAGEMENT.md) for the full
breakdown, the keygen tool, and the third-party agent integration guide.

### Dev / CI mode

Set `USER_IDENTITY_REQUIRED=false` in your `.env` or test fixtures.  Agents
will synthesise a `UserIdentity(user_id="local")` instead of rejecting requests
that lack a `userToken`.  The `prometheus_api` test suite uses this via the
`conftest.py` autouse fixture.

---

## 2. Credentials

### Concept

Instead of reading long-lived `DEEPLYNX_KEY` / `SLURM_JWT_TOKEN` env vars directly,
agents call `self.get_credential(resource)` at execution time.  The broker verifies
**two factors**:

1. **Workload** — that the calling agent is a legitimate platform workload (mTLS
   client certificate, or `VAULT_AGENT_SECRET` header).
2. **User** — the current user's platform JWT, forwarded automatically by
   `get_credential()` from the live `identity_scope`.

```
Agent._execute()
    calls self.get_credential("deeplynx")
        CredentialBroker.get_credential(req, user_token=<jwt>)
            → Vault: verify JWT → per-user policy → fetch secret
            → returns Credential(value={"jwt_token": ...}, expires_at=...)
    agent uses cred.value["jwt_token"] for this single operation
    cred is not cached or stored
```

### Using credentials in `_execute`

```python
from prometheus_api.agent import PrometheusAgent
from prometheus_api.storage_client.connection import ConnectionConfig

class DataAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        # Fetch a per-user DeepLynx credential (JIT, never cached).
        cred = await self.get_credential(
            "deeplynx",
            scope={},   # optional extra params forwarded to broker
        )

        # Build a per-user ConnectionConfig from the credential.
        storage_config = ConnectionConfig.from_credential(cred)

        # Use it for one operation.
        await self.send_deeplynx_artifact(
            context, event_queue,
            file_path=result_path,
            name="analysis-output",
            description="Per-user DeepLynx artifact",
            storage_config=storage_config,
        )
```

### Credential value shapes

| Resource | `cred.value` keys |
|---|---|
| `"deeplynx"` | `jwt_token` (or `key` + `secret`), `org_id`, `project_id` |
| `"slurm"` | `token`, `user`, `slurm_rest_url` |

### Broker backends

Select via `CREDENTIAL_BROKER` env var:

| Value | Class | When to use |
|---|---|---|
| `env` (default) | `EnvCredentialBroker` | Development, single-user, CI |
| `vault` | `VaultCredentialBroker` | Production multi-user |
| `bespoke` | *(install `prometheus_api_credentials_bespoke`)* | Custom backend |

### `env` broker (development)

Reads the same environment variables the platform used before multi-user support.
No Vault required.  All users get the same global credentials.

```
CREDENTIAL_BROKER=env   # or omit (this is the default)
DEEPLYNX_JWT_TOKEN=...
DEEPLYNX_ORG_ID=42
DEEPLYNX_PROJECT_ID=7
SLURM_JWT_TOKEN=...
SLURM_USER=myuser
SLURM_REST_URL=http://slurm.hpc/slurm/v0.0.40
```

### `vault` broker (production)

```
CREDENTIAL_BROKER=vault
VAULT_ADDR=https://vault.example.com
VAULT_JWT_ROLE=prometheus-agent           # Vault JWT auth role
VAULT_JWT_MOUNT=jwt                       # JWT auth mount (default: jwt)
# Workload factor — pick one:
VAULT_AGENT_SECRET=<per-agent-secret>     # simple shared secret header
# or mTLS:
VAULT_MTLS_CERT=/certs/agent.crt
VAULT_MTLS_KEY=/certs/agent.key
VAULT_MTLS_CA=/certs/ca.crt
# Per-user secret paths (templates; {user_id} is substituted):
VAULT_DEEPLYNX_PATH=secret/data/deeplynx/{user_id}   # default
VAULT_SLURM_PATH=secret/data/slurm/{user_id}         # default
```

Vault policy example (per-user, bound to JWT `sub` claim):
```hcl
path "secret/data/deeplynx/{{identity.entity.aliases.auth_jwt.name}}" {
  capabilities = ["read"]
}
```

### Custom broker

Create a package `prometheus_api_credentials_bespoke` with a top-level `Broker` class:

```python
# prometheus_api_credentials_bespoke/__init__.py
from prometheus_api.credentials.broker import Credential, CredentialBroker, CredentialRequest

class Broker:
    async def get_credential(
        self,
        req: CredentialRequest,
        *,
        user_token: str,
    ) -> Credential:
        ...
```

Install it alongside `prometheus_api` and set `CREDENTIAL_BROKER=bespoke`.

---

## 3. Per-user worker isolation

### Why

A shared asyncio process is safe for data isolation but not for secret isolation.
If an agent holds a live per-user credential across `await` boundaries, a memory
inspection or bug could expose it to concurrent users.  Worker isolation moves each
user's requests into a dedicated OS process; a bug in user A's process cannot touch
user B's memory.

### Opting in

Set the class attribute on any agent that calls `get_credential()` and performs
multi-step async work with the credential:

```python
class HpcAgent(PrometheusAgent):
    requires_user_isolation = True   # run _execute in a per-user subprocess

    async def _execute(self, params, context, event_queue):
        cred = await self.get_credential("slurm")
        # submit job, poll status, etc.
        ...
```

When `requires_user_isolation = True`, the `UserWorkerPool` supervisor spawns one
subprocess per `user_id` (lazily, on first request) and routes requests there.
Each worker re-enters an `identity_scope` for its assigned user.

### Worker lifecycle

```
First request for user "alice"
    → UserWorkerPool._get_or_spawn("alice")
    → subprocess spawned: prometheus-user-worker-alice (PID 1234)

Subsequent requests for "alice" → routed to same process

After USER_WORKER_IDLE_TTL seconds of inactivity
    → reaper terminates the process
    → next request spawns a fresh one
```

| Variable | Default | Description |
|---|---|---|
| `USER_WORKER_IDLE_TTL` | `300` | Seconds idle before a worker exits |
| `USER_WORKER_MAX` | `32` | Maximum concurrent worker processes |

### Agents that should NOT opt in

- Stateless agents that only read params and call LLM/search — no secrets held.
- Agents that use `get_credential()` and immediately complete in one `await` — the
  secret exposure window is negligible.
- The client-agent orchestrator itself — it fetches JIT and forwards the JWT; it
  never holds a user's third-party credential across turns.

---

## 4. Conversation ownership

Every conversation is bound to the user who created it.  Subsequent requests from a
different user to the same `conversation_id` are rejected.  The client-agent enforces
this at its entry point; specialist agents inherit the protection because they always
receive `conversation_id` from a client-agent turn.

```
First turn:  user "alice", conversation_id "abc-123"
    → record_conversation_owner("abc-123", "alice")

Second turn:  user "bob", conversation_id "abc-123"
    → assert_conversation_owner("abc-123", "bob")
    → PermissionError: Conversation 'abc-123' is owned by a different user
```

Redis keys:
- `conv_owner:{conversation_id}` — the owning user_id
- `user:convs:{user_id}` — set of conversation_ids owned by the user (used for `/history`)

---

## 5. Interaction diagram (full request flow)

```
Browser (user "alice")
  │ POST /api/chat/messages
  ▼
Platform backend
  ├─ mint JWT: { sub: "alice", exp: now+2h }   (signed with USER_IDENTITY_PRIVATE_KEY)
  ├─ embed in message.metadata["userToken"]
  └─ POST A2A message/send → client-agent

client-agent (OrchestratorAgent._execute)
  ├─ _extract_identity() → verify_user_token() → identity_scope("alice")
  ├─ record_conversation_owner(conv_id, "alice")   or assert if existing
  ├─ params["user_id"] = "alice"
  ├─ routes to specialist agents, propagating userToken in each A2A call
  └─ may call self.get_credential("deeplynx") → broker → per-user JIT token

Specialist agent (e.g. data-agent)
  ├─ _extract_identity() → verify_user_token() → identity_scope("alice")
  ├─ params["user_id"] = "alice"   (verified again end-to-end)
  └─ calls self.get_credential("deeplynx") → broker → per-user DeepLynx token
```

---

## See also

- [IDENTITY_KEY_MANAGEMENT.md](./IDENTITY_KEY_MANAGEMENT.md) — RS256 key generation and distribution, third-party agent integration, key rotation
- [PrometheusAgent Developer Guide](GUIDE.md) — general agent authoring
- [QUICK_START.md](QUICK_START.md) — minimal working agent
- Platform docs: `prometheus_platform/docs/dev-docs/multi-user-setup.md`
