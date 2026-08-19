# 00 — Deployment blocker: JWT secret delivery + Redis auth consistency

**Findings:** BLK-3 `[REG]` (release blocker), DEP-1 `[CARRY]`.
**Depends on:** —. **Verify:** `make up` brings a healthy `chat-backend`; `POST /api/auth/login` succeeds via curl.
**Status:** ✅ Implemented (docker-compose.yml, chat-backend/app/main.py, chat-backend/app/config.py, .env.example; tests in chat-backend/tests/test_config.py). See the Progress log in `README.md`. Not yet exercised via a live `make up` (Docker) — only unit-verified.

## BLK-3 — JWT secret never reaches the container → login 500s

Today `docker-compose.yml` passes only `CHAT_BACKEND_JWT_SECRET: ${CHAT_BACKEND_JWT_SECRET:-}`
to the service (blank default in `.env.example`). The documented fallback
`CHAINLIT_AUTH_SECRET` is **not** in `x-common-env` and not on the chat-backend service, so
inside the container both are empty → `config._jwt_secret` returns `""` →
`security.issue_token` raises `RuntimeError` at *login time* as an unhandled 500.

Fix (both halves):

1. **Deliver a secret.** Add `CHAINLIT_AUTH_SECRET: ${CHAINLIT_AUTH_SECRET:-}` to the
   `chat-backend` service `environment:` block (it already reads it as a fallback in
   `chat-backend/app/config.py:44-50`), keeping the existing `CHAT_BACKEND_JWT_SECRET`
   line. In `.env.example`, document that one of the two must be set and give a generate
   hint (`openssl rand -hex 32`).
2. **Fail fast, loudly, at startup — not at first login.** In `chat-backend/app/main.py`
   lifespan/startup, assert a non-empty resolved JWT secret and raise a clear error if
   missing (so a misconfigured deploy crashes on boot with an actionable message instead
   of 500ing the first user). Keep the `RuntimeError` in `security.issue_token` as a
   backstop.

Files: `docker-compose.yml` (chat-backend env), `.env.example`, `chat-backend/app/main.py`.

## DEP-1 — REDIS_PASSWORD passed but unread; NOAUTH risk

`chat-backend/app/config.py:65` reads only `REDIS_URL`. `x-common-env` passes both
`REDIS_URL` (default `redis://redis:6379`, no creds) and `REDIS_PASSWORD`. Any deploy that
sets `REDIS_PASSWORD` while leaving `REDIS_URL` at the compose default authenticates with
no password → `NOAUTH` on all Redis-backed features (SSE task events, `/api/conversations/recent`).

Fix (pick the lower-risk option, matching how the rest of the stack consumes Redis): either
(a) fold `REDIS_PASSWORD` into the URL when present and the URL carries no userinfo, in
`config.py`; or (b) document in `.env.example` that `REDIS_URL` must embed the password
(the current `.env.example:19` form) and drop the unused `REDIS_PASSWORD` from the
chat-backend env to remove the footgun. Prefer (a) if other services already accept a bare
`REDIS_PASSWORD`; otherwise (b).

Files: `chat-backend/app/config.py` and/or `docker-compose.yml` + `.env.example`.

## Not here (owned by `../frontend/README.md` Step 09)

BLK-2 (`frontend-react/nginx1.conf` → proxy `/api/` to `chat-backend`, add SSE tuning,
drop dead `chainlit-frontend` locations) and BLK-4 (Vite `/api` dev proxy + repoint
`VITE_CHAINLIT_SERVER`→backend). Called out so this step isn't mistaken as "makes prod
serve the SPA" — it only makes the backend itself bootable and authenticable.

## Verify

- `docker compose config` resolves; `make up`; `chat-backend` container healthy (no
  startup crash, or a *clear* crash if the secret is unset).
- `curl -sS -X POST :8600/api/auth/login -d '{"username":"…","password":"…"}' -H 'Content-Type: application/json' -i`
  returns 200 + `Set-Cookie`, not 500.
- With `REDIS_PASSWORD` set, `/api/conversations/recent` does not `NOAUTH`.
