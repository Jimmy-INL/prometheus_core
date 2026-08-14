# Identity Key Management

This page covers the choice between HS256 and RS256, which environment variables
go where, and how to integrate a trusted third-party agent without sharing any
private material.

---

## HS256 vs RS256 — what the choice actually means

| | HS256 (symmetric HMAC) | RS256 (asymmetric RSA) |
|---|---|---|
| **Signing key** | One shared secret | Private key (kept secret) |
| **Verification key** | Same shared secret | Public key (safe to distribute) |
| **Who can mint a token?** | Anyone holding the secret | Only whoever holds the private key |
| **Who can verify a token?** | Anyone holding the secret | Anyone with the public key |
| **If an agent is compromised** | Attacker can forge tokens for any user | Attacker can only verify — cannot forge |
| **Third-party agents** | ❌ Require sharing the secret | ✅ Need only the public key |
| **Key rotation** | All services must restart together | Agents poll JWKS; zero-downtime rotation |
| **When to use** | Fully-internal, single-operator deployments | Production; any third-party integration |

**Rule of thumb:** use HS256 for local dev and single-operator internal networks.
Use RS256 as soon as a third party (different team, vendor, or org) registers an
agent, or whenever you want rotation without coordinating restarts.

---

## Where each env var must be set

### HS256 — one secret, everywhere

The same secret is used to both sign and verify, so it must be present on
every service that participates in the identity chain.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Service                     Required env var                        │
├──────────────────────────────────────────────────────────────────────┤
│  Frontend (Chainlit)         USER_IDENTITY_SECRET   ← mints tokens  │
│  Client-agent                USER_IDENTITY_SECRET   ← verifies      │
│  Specialist agents           USER_IDENTITY_SECRET   ← verifies      │
│  Third-party agents          USER_IDENTITY_SECRET   ← CANNOT USE    │
└──────────────────────────────────────────────────────────────────────┘
```

Every service that knows `USER_IDENTITY_SECRET` can forge a token for any
`user_id`.  Keep the set of services that hold this secret as small as possible.

### RS256 — private key only on the frontend; public key everywhere

The private key is used only to mint tokens (sign).  Verification uses only
the public key.  Agents never need the private key.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Service                     Required env var                        │
├──────────────────────────────────────────────────────────────────────┤
│  Frontend (Chainlit)         USER_IDENTITY_PRIVATE_KEY  ← mints     │
│                              USER_IDENTITY_PUBLIC_KEY   (optional,  │
│                                                          but safe)  │
│  Client-agent                USER_IDENTITY_PUBLIC_KEY   ← verifies  │
│  Specialist agents           USER_IDENTITY_PUBLIC_KEY   ← verifies  │
│  Third-party agents          USER_IDENTITY_PUBLIC_KEY   ← verifies  │
│                              (or fetched from JWKS endpoint)        │
└──────────────────────────────────────────────────────────────────────┘
```

The public key is safe to distribute openly.  A third-party agent can verify
that a `userToken` was signed by *this* platform without any private material.

#### Setting the keys

```bash
# Generate a 2048-bit (minimum) or 4096-bit RSA key pair:
openssl genrsa -out identity_private.pem 4096
openssl rsa -in identity_private.pem -pubout -out identity_public.pem

# Frontend .env — only this service needs the private key:
USER_IDENTITY_ALG=RS256
USER_IDENTITY_PRIVATE_KEY="$(cat identity_private.pem)"

# All agents .env — public key only:
USER_IDENTITY_ALG=RS256
USER_IDENTITY_PUBLIC_KEY="$(cat identity_public.pem)"
```

Multi-line PEM values in Docker Compose env blocks need careful quoting.
Use a secret manager or pass the file path and load it in a startup script
rather than embedding the raw PEM in compose YAML.

---

## Third-party agent integration

A "third-party agent" is any agent operated by a different team, vendor, or
organization — one that you cannot share a secret or private key with.

### The problem with HS256

If you give a third party `USER_IDENTITY_SECRET`, they can construct a
`UserIdentity` for `user_id="admin"` and call your platform as that user.
The secret must **never** leave your org.

### RS256 with a shared public key

With RS256, the third party needs only the public key.  They cannot forge
tokens; they can only verify that a token was genuinely signed by your platform.

**Distribution options** (pick one):

**Option A — Give them the public key directly.**
Copy `identity_public.pem` to the third-party operator.  They set it as
`USER_IDENTITY_PUBLIC_KEY`.  Simple, but requires manual coordination on
key rotation.

**Option B — Serve a JWKS endpoint (recommended).**  
The platform exposes the public key as a
[JSON Web Key Set](https://datatracker.ietf.org/doc/html/rfc7517) at
`GET /.well-known/jwks.json`.  Third-party agents fetch this at startup and
refresh it periodically, so key rotation is transparent.

> **Current status:** the JWKS endpoint is not yet implemented.  Until it is,
> use Option A and coordinate key rotation manually.  Adding it requires
> a small addition to `PrometheusAgent.build_app()`: a new Starlette route at
> `/.well-known/jwks.json` that serialises `USER_IDENTITY_PUBLIC_KEY` with
> `jwcrypto` or `python-jose`.  The agent's `verify_user_token` would then
> also accept a `JWKS_URL` override to fetch and cache keys remotely.

### What the third-party agent needs to configure

```bash
# Third-party agent .env
USER_IDENTITY_ALG=RS256
USER_IDENTITY_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"
USER_IDENTITY_ISS=prometheus-platform   # must match what the platform sets
USER_IDENTITY_AUD=prometheus-agents     # must match what the platform sets
USER_IDENTITY_REQUIRED=true
```

`USER_IDENTITY_ISS` and `USER_IDENTITY_AUD` are validated on every token.
Agree on these values with the third party in advance; a token minted with a
different issuer will be rejected.

### What the third-party agent does NOT need

- `USER_IDENTITY_SECRET` — this is HS256 only; irrelevant for RS256.
- `USER_IDENTITY_PRIVATE_KEY` — agents only verify, they never mint.
- Any platform credentials (Redis password, agent secret, DeepLynx keys) — those
  are separate from identity and governed by the existing `AGENT_SECRET` bearer
  token that LiteLLM enforces on every inbound call.

### Full trust chain for a third-party agent request

```
User "alice" logs in via platform frontend
    ↓
Frontend mints JWT: { sub: "alice", iss: "prometheus-platform",
                      aud: "prometheus-agents", exp: now+2h }
                    signed with platform PRIVATE key
    ↓
client-agent forwards JWT in message.metadata["userToken"]
    ↓
Third-party agent receives the A2A request
    verifies JWT against platform PUBLIC key
    → confirms: this request is from a genuine platform user named "alice"
    → cannot forge a different user
    → cannot call other platform internals (no Redis, no agent secret)
```

---

## Key rotation

### HS256

All services holding `USER_IDENTITY_SECRET` must restart at the same time.
Any in-flight tokens (background turns, long-running jobs) will be rejected
after the rotation.  Plan a maintenance window or use a generous overlap period:
run both secrets simultaneously by updating `verify_user_token` to accept
a list of valid secrets (not currently implemented).

### RS256 + JWKS (once implemented)

1. Generate a new key pair.
2. Add the new public key to the JWKS endpoint (keep both old and new key IDs
   active during the overlap window — the JWT `kid` header selects which one
   to verify against).
3. Update the frontend to sign with the new private key.
4. Agents fetching from JWKS pick up the new key automatically.
5. After all tokens signed with the old key have expired, remove the old key
   from the JWKS.

Zero downtime, no coordinated restarts, third-party agents unaffected.

---

## Quick reference

| Scenario | Algorithm | Frontend | Agents | Third-party agents |
|---|---|---|---|---|
| Local dev / single-operator | HS256 | `USER_IDENTITY_SECRET` | `USER_IDENTITY_SECRET` | ❌ not possible |
| Internal production | RS256 | `USER_IDENTITY_PRIVATE_KEY` | `USER_IDENTITY_PUBLIC_KEY` | `USER_IDENTITY_PUBLIC_KEY` |
| With third-party agents | RS256 + JWKS | `USER_IDENTITY_PRIVATE_KEY` | `USER_IDENTITY_PUBLIC_KEY` or JWKS URL | JWKS URL or public key |

---

## See also

- [MULTI_USER.md](./MULTI_USER.md) — full identity and credential reference
- [AGENT_MIGRATIONS.md](./AGENT_MIGRATIONS.md) — 0.10.0 migration steps
- [ENV_SETUP.md](../ENV_SETUP.md) — environment variable reference
- Platform docs: `prometheus_platform/docs/dev-docs/multi-user-setup.md`
