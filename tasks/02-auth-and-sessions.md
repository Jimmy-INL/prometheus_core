# 02 — Auth, session store, config & sessions endpoints

> **Status: ✅ Done** (2026-08-10) — created `app/security.py`, `app/sessions.py`,
> `app/routers/{auth,config,sessions}.py`; extended `contract.py` additively with
> `ChatProfile` + `profile`/`profiles` fields; mounted the routers and put the
> `SessionStore` on `app.state` in `main.py`. Added the `python-multipart` runtime
> dep (FastAPI needs it to read form-encoded login bodies).
>
> **Verification:** `ruff check app/` and `mypy app/` clean. Live matrix (uvicorn on
> :8600, `CHAT_BACKEND_JWT_SECRET` set): JSON + form login → 200 with an
> `HttpOnly; SameSite=lax; Secure; Max-Age=86400` cookie; `GET /api/auth/me` returns
> the user with the cookie and 401 without; bad creds → 401; `POST /api/sessions`
> mints a fresh `conversation_id` on each call under the same identity and 401s
> unauthenticated; `GET /api/config` returns profiles + suggestions from `config.yml`;
> logout clears the cookie; `GET /api/auth/callback/{provider}` → 501. `uv sync` still
> can't resolve the `prometheus_api` git dep locally (environmental, same as task 00);
> task-02 code imports none of it, so verification used a throwaway venv of the direct
> deps.

## Goal

Password auth with a JWT httpOnly cookie, an in-memory per-session state store, and the
session bootstrap endpoints (`/api/config`, `/api/sessions`) that replace Chainlit's
`on_chat_start` / `set_chat_profiles`.

## Files to create

- `chat-backend/app/security.py`
- `chat-backend/app/sessions.py`
- `chat-backend/app/routers/auth.py`
- `chat-backend/app/routers/config.py`
- `chat-backend/app/routers/sessions.py`

## Details

### `security.py`
- Port `auth_callback` logic from `frontend/main.py:31` — check `username`/`password` against
  `settings.local_users` (plaintext compare, same as today; note the weakness but preserve
  behavior).
- `issue_token(user) -> str` / `verify_token(token) -> claims` using `pyjwt` and
  `settings.jwt_secret`. Claims: `sub` (username), `role`, `sid` (session id = new uuid),
  `exp`.
- FastAPI dependency `current_user` that reads the cookie (`settings.cookie_name`), verifies,
  and returns claims; raises 401 otherwise.
- **`IdentityProvider` protocol** — abstract `authenticate()` / `callback()` so the current
  password provider and a future OAuth provider share a shape. The Chainlit `oauth_callback`
  (main.py:22) is a pass-through today; model the interface but only implement password now.
  Reserve `GET /api/auth/callback/{provider}` (stub 501).

### `sessions.py`
- In-memory `SessionStore` keyed by `sid`: `conversation_id`, `artifacts: list[dict]`,
  `awaited_task_ids: set[str]`, `profile: str`. Mirrors the `cl.user_session` keys
  (`conversation_id`, `artifacts`, `backgrounded_task_ids`, `chat_profile`).
- Lost on restart — documented, same as Chainlit today.

### `routers/auth.py`
- `POST /api/auth/login` — accept form or JSON `{username, password}`; on success set the JWT
  cookie (httpOnly, SameSite=Lax, Secure in prod) and return `{user}`; 401 on failure.
- `POST /api/auth/logout` — clear the cookie.
- `GET /api/auth/me` — return current user (or 401). Replaces the React app's `fetch("/user")`.

### `routers/config.py`
- `GET /api/config` — chat profiles (Beginner/Advanced, from `main.py` `chat_profile`),
  `workflow_suggestions`, `chat_intro`, `chat_suggestion_title`, `max_upload_bytes`,
  `auto_approve_steps`. All from settings.

### `routers/sessions.py`
- `POST /api/sessions` — requires auth; create a `conversation_id` (uuid), store in the
  session, return `{conversation_id, profile, chat_intro, suggestions}`. If profile is
  "Beginner Chat", include suggestions (parallels `on_chat_start`).

## Acceptance check

- `POST /api/auth/login` with `prometheus/prometheus` (from config.yml) sets a cookie;
  `GET /api/auth/me` returns the user; bad creds → 401.
- `POST /api/sessions` returns a fresh `conversation_id`; a second call reuses the session's
  identity but can mint a new conversation.
- `GET /api/config` returns the suggestions list from `config.yml`.
