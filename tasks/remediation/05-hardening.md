# 05 — Hardening (carried-over weaknesses + lower-severity items)

**Findings:** AU-3 `[CARRY]`, AU-1 `[CARRY]`, AU-2 `[CARRY]`, AU-5 `[REG]`, AU-7 `[REG]`, AU-8 `[GAP]`, AU-9 `[CARRY]`, AU-6 `[GAP]`.
**Depends on:** 00–04. **Verify:** `test_auth`/`test_sessions`/`test_conversations` suites + new cases green.
**Status:** ✅ Implemented (app/security.py, app/routers/{auth,config,sessions,conversations}.py, app/conversation_state.py, app/config.py, app/main.py; tests in test_auth.py + test_sessions.py + test_conversations.py). AU-1 = process-local revocation set (logout revokes the sid; `current_claims` rejects it). AU-2 = sort-before-slice. AU-3 = `hmac.compare_digest` constant-time compare. AU-5 = `/api/config` auth-gated. AU-6 = provider registry seam (`get_provider`/`register_provider`; OAuth still 501). AU-7 = client reused across requests (cached by class object). AU-8 = profile validated against `CHAT_PROFILES` (422 on unknown). AU-9 = explicit dev CORS origins (no credentialed wildcard). **Deferred with rationale:** AU-3 *hashed-at-rest* storage (plaintext local-users are dev-only; needs a hashing dependency + config migration — production should use the OAuth/IdP seam). Revocation set + session store are in-memory (lost on restart), same as the rest of the service.

Included per the "fix carryovers too" decision — these are not migration regressions
(except AU-5/AU-7) but this is a pre-release pass. Order within the step by risk.

## AU-3 — Password hashing + constant-time compare

`security.py:91` compares plaintext (`==`) against cleartext secrets in `config.yml`. Fix:
store password **hashes** (bcrypt/argon2 via `passlib`, or stdlib `hashlib.scrypt`) and
verify with the library's constant-time check; at minimum wrap the current compare in
`hmac.compare_digest` and move secrets out of `config.yml` into env/secret. Migrate
`local_users` config format accordingly and document it. Test: correct/incorrect password;
timing-independent compare in use.

## AU-1 — Logout actually invalidates the session

`current_claims`/`current_user` (`security.py:140,154`) are stateless; `logout`
(`auth.py:92`) only deletes the cookie, so a retained token works until `exp` (~24h). Fix:
add a server-side revocation set (store the `sid`/jti in the `SessionStore`/Redis on
logout and reject revoked tokens in `current_claims`), or shorten TTL + add refresh. Test:
a token used after logout is rejected.

## AU-2 — Recent-history: sort before slice

`conversation_state.py:44` slices `keys[:limit]` from unordered `KEYS` before sorting by
timestamp (`:60`) → newest conversations can be excluded. Fix: fetch timestamps for all
candidate keys (or maintain a sorted index), sort, then slice. Watch cost on large
keyspaces — consider a capped `SCAN` + sorted set index if needed. Test: with > limit
conversations, the newest `limit` are returned.

## AU-5 — Authenticate `/api/config`

`config.py:36` `get_config` has no auth dependency; it leaks profiles/suggestions/limits
that were behind login before. Fix: add the same `current_claims` dependency as
`/api/sessions`. (If the frontend needs *some* config pre-login, split into a tiny public
subset vs. the authenticated remainder — coordinate with Bucket A.) Test: unauthenticated
`/api/config` → 401.

## AU-7 — Reuse the Redis connection for history

`conversations.py:36` builds a new `ConversationStateClient(...)` (with `.ping()`) per
request. Fix: construct once (module-level or app state / dependency) and reuse. Test:
handler uses the shared client.

## AU-8 — Validate the client-supplied `profile`

`sessions.py:51` stores any `body.profile` string unchecked; unknown values silently fall
to "advanced" behavior. Fix: validate against `CHAT_PROFILES`; reject/normalize unknowns.
Test: an unknown profile → 422 or explicit default.

## AU-9 — Dev CORS: no wildcard-with-credentials

`main.py:29` sets `allow_origins=["*"]` with `allow_credentials=True` (debug-gated).
Browsers reject credentialed wildcard. Fix: in debug, enumerate the dev origin(s)
explicitly (e.g. the Vite dev URL) with credentials, instead of `*`. Test: config assertion.

## AU-6 — Make the OAuth provider actually pluggable (or mark clearly deferred)

`IdentityProvider` is a `Protocol` but nothing dispatches through it; the callback route
hard-raises 501 (`auth.py:112`). Minimum: a provider registry `current_claims`/login can
select, with `password_provider` as the default entry — even if OAuth stays a 501 stub, the
seam should be real. If deferring, replace the aspirational docstrings with an explicit
"not implemented; see Bucket A / Okta follow-up" note so it isn't mistaken for working.

## Verify

`cd chat-backend && uv run pytest && uv run ruff check && uv run mypy app/` (full suite).
