# Identity Key Management

This page covers RS256 key generation, which environment variables go where, and
how to integrate a trusted third-party agent without sharing any private material.

Signing is **RS256 only** — there is no symmetric-secret (HS256) option. A shared
secret would let any agent holding it forge a token for any user; with RS256, only
the platform backend (which holds the private key) can mint tokens, and every
verifying agent — including third-party ones — needs only the public key or a
JWKS URL, neither of which can be used to forge anything.

---

## Generating a keypair

### Option A — the built-in keygen tool (recommended)

`prometheus_api` ships a keygen module and console script, available in every
agent container built `FROM` the base image — no extra installation needed:

```bash
# Print both keys plus a ready-to-paste .env snippet:
prometheus-identity-keygen

# Or write PEM files instead:
prometheus-identity-keygen --out-dir ./keys
# → ./keys/identity_private.pem  (0600 permissions — keep secret)
# → ./keys/identity_public.pem   (safe to distribute)

# Larger key (default is 4096 bits; 2048 is the practical minimum for RS256):
prometheus-identity-keygen --key-size 4096 --out-dir ./keys
```

Equivalent module invocation if the console script isn't on `PATH`:
```bash
python -m prometheus_api.agent.identity_keygen --out-dir ./keys
```

Or programmatically:
```python
from prometheus_api.agent.identity_keygen import generate_keypair
private_pem, public_pem = generate_keypair(key_size=4096)
```

### Option B — plain openssl (zero dependencies)

```bash
openssl genrsa -out identity_private.pem 4096
openssl rsa -in identity_private.pem -pubout -out identity_public.pem
```

Both options produce the same thing: two PEM files, unencrypted, no passphrase.

---

## Where each env var must be set

The private key is used only to **mint** tokens. The public key (or a JWKS URL) is
used only to **verify** them. Nothing that can forge a token needs to leave the
platform backend.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Service                     Required env var                        │
├──────────────────────────────────────────────────────────────────────┤
│  Platform backend            USER_IDENTITY_PRIVATE_KEY  ← mints     │
│  Client-agent                USER_IDENTITY_PUBLIC_KEY    ← verifies  │
│  Specialist agents           USER_IDENTITY_PUBLIC_KEY    ← verifies  │
│  Third-party agents          USER_IDENTITY_PUBLIC_KEY    ← verifies  │
│                              (or JWKS_URL — see below)               │
└──────────────────────────────────────────────────────────────────────┘
```

The public key is safe to distribute openly. A third-party agent can verify that a
`userToken` was signed by *this* platform without ever holding private material.

#### Setting the keys

```bash
# Backend .env — only this service needs the private key:
USER_IDENTITY_PRIVATE_KEY="$(cat identity_private.pem)"

# All agents .env — public key only:
USER_IDENTITY_PUBLIC_KEY="$(cat identity_public.pem)"
```

Multi-line PEM values in Docker Compose env blocks need careful quoting.
Use a secret manager or pass the file path and load it in a startup script
rather than embedding the raw PEM in compose YAML.

**Single-host / local dev shortcut:** if `USER_IDENTITY_PUBLIC_KEY` is unset,
`verify_user_token` derives the public key from `USER_IDENTITY_PRIVATE_KEY`
automatically — convenient when the same process mints and verifies (e.g. running
the backend and a specialist agent on one machine for local testing), but don't
rely on this in production: verifying services should not need the private key.

---

## Third-party agent integration

A "third-party agent" is any agent operated by a different team, vendor, or
organization — one that you cannot share private material with. RS256 makes this
straightforward: give them only the public key, or point them at your JWKS
endpoint.

**Distribution options** (pick one):

### Option A — Give them the public key directly

Copy `identity_public.pem` to the third-party operator. They set it as
`USER_IDENTITY_PUBLIC_KEY`. Simple, but requires manual coordination on key
rotation.

### Option B — Serve and consume the JWKS endpoint (recommended)

Every `PrometheusAgent` serves the platform's public key at
`GET /.well-known/jwks.json`. This endpoint:

- Is unauthenticated (no `Authorization` header required) — same as `/.well-known/agent.json`.
- Returns the RSA public key as a JWK with `kid`, `use`, and `alg`.
- Returns `{"keys": []}` when no key is configured.
- Minted tokens carry a `kid` header so verifiers can select the right key
  when multiple keys are present (key rotation overlap window).

Third-party agents verify tokens using the JWKS URL:

```bash
# Third-party agent .env
JWKS_URL=https://prometheus.example.com/.well-known/jwks.json
USER_IDENTITY_ISS=prometheus-platform
USER_IDENTITY_AUD=prometheus-agents
USER_IDENTITY_REQUIRED=true
```

`verify_user_token` uses PyJWT's `PyJWKClient` internally: it fetches the JWKS,
caches the keys (TTL: 1 hour), and automatically refreshes when it encounters an
unknown `kid`. No `USER_IDENTITY_PUBLIC_KEY` needed on the third-party side.

### What the third-party agent needs to configure

**Option A — static public key:**
```bash
# Third-party agent .env
USER_IDENTITY_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"
USER_IDENTITY_ISS=prometheus-platform   # must match what the platform sets
USER_IDENTITY_AUD=prometheus-agents     # must match what the platform sets
USER_IDENTITY_REQUIRED=true
```

**Option B — JWKS URL (recommended; handles key rotation automatically):**
```bash
# Third-party agent .env
JWKS_URL=https://prometheus.example.com/.well-known/jwks.json
USER_IDENTITY_ISS=prometheus-platform
USER_IDENTITY_AUD=prometheus-agents
USER_IDENTITY_REQUIRED=true
```

`USER_IDENTITY_ISS` and `USER_IDENTITY_AUD` are validated on every token. Agree on
these values with the third party in advance; a token minted with a different
issuer will be rejected.

### What the third-party agent does NOT need

- `USER_IDENTITY_PRIVATE_KEY` — agents only verify, they never mint.
- Any platform credentials (Redis password, agent secret, DeepLynx keys) — those
  are separate from identity and governed by the existing `AGENT_SECRET` bearer
  token that LiteLLM enforces on every inbound call.

### Full trust chain for a third-party agent request

```
User "alice" logs in via the platform frontend
    ↓
Platform backend mints JWT: { sub: "alice", iss: "prometheus-platform",
                               aud: "prometheus-agents", exp: now+2h }
                             signed with USER_IDENTITY_PRIVATE_KEY
    ↓
client-agent forwards JWT in message.metadata["userToken"]
    ↓
Third-party agent receives the A2A request
    verifies JWT against USER_IDENTITY_PUBLIC_KEY (or via JWKS_URL)
    → confirms: this request is from a genuine platform user named "alice"
    → cannot forge a different user (never had the private key)
    → cannot call other platform internals (no Redis, no agent secret)
```

---

## Key rotation

Each minted token carries a `kid` header matching the key ID in the JWKS.
`PyJWKClient` selects the right key automatically, so an overlap window with two
simultaneously valid keys works out of the box.

1. Generate a new keypair (`prometheus-identity-keygen`).
2. Update `USER_IDENTITY_PUBLIC_KEY` on all platform agents to contain the **new**
   public key. The JWKS endpoint immediately serves the new key. Tokens minted with
   the old private key are still verifiable until they expire — but because `kid`
   changed, `PyJWKClient` will do a JWKS refresh automatically on first encounter.
3. Update `USER_IDENTITY_PRIVATE_KEY` on the backend to the new private key. New
   tokens are now minted with the new key/kid.
4. Wait for `USER_IDENTITY_TTL` seconds (the longest outstanding token lifetime).
5. Remove the old private key from any backups.

Zero downtime, no coordinated restarts for agents fetching from `JWKS_URL`.
Third-party agents are unaffected as long as their `JWKS_URL` points to the
platform — `PyJWKClient` re-fetches on unknown `kid`.

---

## Quick reference

| Service | Env var | Purpose |
|---|---|---|
| Platform backend | `USER_IDENTITY_PRIVATE_KEY` | Mint tokens |
| Every agent (internal) | `USER_IDENTITY_PUBLIC_KEY` | Verify tokens |
| Third-party agent | `JWKS_URL` (recommended) or `USER_IDENTITY_PUBLIC_KEY` | Verify tokens without manual key distribution |
| Backend + every agent | `USER_IDENTITY_ISS`, `USER_IDENTITY_AUD` | Must match across all services |
| Backend only | `USER_IDENTITY_TTL` | Minted-token lifetime |
| Every agent | `USER_IDENTITY_REQUIRED` | `false` only for local dev / smoke tests |

---

## See also

- [MULTI_USER.md](./MULTI_USER.md) — full identity and credential reference
- [AGENT_MIGRATIONS.md](./AGENT_MIGRATIONS.md) — migration steps, including HS256 removal
- [ENV_SETUP.md](../ENV_SETUP.md) — environment variable reference
- Platform docs: `prometheus_platform/docs/dev-docs/multi-user-setup.md`
