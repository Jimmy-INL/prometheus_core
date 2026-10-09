# Pre-PR review — `old-frontend-removal`

**Point-in-time verification record. May go stale — read it against the commit below.**

- **Branch:** `old-frontend-removal`
- **Reviewed at commit:** `738008b` ("Merge origin/dev into old-frontend-removal; apply branch review fixes")
- **Date:** 2026-08-20
- **Reviewer:** Claude Code (fan-out review: 3 exploration passes → offline gates → live `make up` smoke → 7-dimension adversarial bug-hunt workflow with refute-first verification)
- **Scope of the branch:** removes the legacy Chainlit `frontend/`, moves the React app `frontend-react/` → `frontend/`, and adds a new FastAPI `backend/` service that owns its own JSON/SSE wire contract (`backend/CONTRACT.md` / `backend/app/contract.py`).
- **Review goal:** no newly-introduced bugs; feature parity with the pre-migration app (explicitly *not* new features). Known migration gaps were pre-accepted as follow-ups (see [Accepted follow-ups](#accepted-follow-ups)).

---

## Verdict

The migration is **structurally sound and has no true merge-blocker.** It builds, boots live, is unit-green, and the core wire contract works end-to-end against a running stack. The bug-hunt's headline "blocker" was a **false positive** (see [Investigated and dismissed](#investigated-and-dismissed)).

What remains is a cluster of real but previously-untested async/SSE bugs (concentrated in the *backgrounded-task* delivery path) plus an HTTP-cookie auth issue. None block the migration itself. **Safe to PR**, provided the auth-cookie item is fixed before any non-localhost / non-TLS deployment, and the backgrounded-task cluster is fixed or consciously accepted.

---

## What was run

| Gate | Result |
|---|---|
| Backend `pytest` (offline) | **174 passed** |
| Backend `mypy app/` | **clean** (25 files) |
| Backend `ruff check app/` | **clean** |
| `chainlit` imports under `backend/` | **none** |
| Frontend `eslint` (`--max-warnings 0`) | **clean** |
| Frontend `tsc --noEmit` | **clean** |
| Frontend unit tests (`node:test`) | **4/4 pass** |
| Frontend `vite build` | **✓** (~17.7s) |
| Live `make up` | **stack boots healthy** — `backend`, `client-agent`, `synthesis`/`osti`/`form-filler` agents, `litellm-proxy` (healthy), `litellm-db` (healthy), `agent-valkey` |
| Live contract matrix | `healthz`, `login`, `me`, `config`, `sessions`, `conversations/recent`, `events` (SSE, `text/event-stream`), `uploads`, **`chat` → `completed` with a real LLM-generated report** — all ✅ |

This retires the authors' repeatedly-flagged "#1 risk" (*never run live*): the backend provably boots and serves the contract, and a real LLM-backed chat turn completed correctly against the live client-agent.

### How to reproduce the gates

- **Backend (note the stale-venv caveat below):** `cd backend && ./.venv/bin/python -m pytest -q` (also `-m mypy app/`, `-m ruff check app/`).
- **Frontend:** `cd frontend && npm run lint && npm run typecheck && npm run build && node --test 'src/**/*.test.ts'`.
- **Live:** `PROMETHEUS_API_BASE_IMAGE_HASH=latest make up`, then `cd backend && ./.venv/bin/python scripts/smoke.py --base-url http://localhost:8600` (see the auth-cookie finding — `smoke.py` currently can't get past login over HTTP).

---

## Findings (newly-introduced, ranked)

Confidence is marked **LIVE** (empirically reproduced against the running stack) or **code-analysis** (traced through source + adversarially verified, but not live-triggered).

### 🔴 HIGH — Auth breaks over HTTP for spec-compliant clients — *LIVE*
- **Where:** `backend/app/routers/auth.py:50` (`secure=not settings.debug`), `backend/app/config.py:110` (`debug` comes only from `config.yml`, no env override), `backend/app/config.yml:28` (`debug: false`).
- **What:** the session cookie is set `Secure`, but the default `make up` stack serves plain HTTP. `login` succeeds and sets `prometheus_session`, but `GET /api/auth/me` returns **401** for any spec-compliant client — reproduced live with `httpx`/`smoke.py`. `curl` and browsers on `http://localhost` are spared only by localhost secure-context leniency; **non-localhost HTTP deployments and all programmatic clients (including the project's own `smoke.py`) are broken.**
- **Recommended fix (flagged, not auto-applied — security-design decision):** add a dedicated env override (e.g. `BACKEND_COOKIE_SECURE`, or make `debug` env-overridable, matching the existing per-key override pattern in `config.py`) and set it appropriately for the dev compose so the HTTP stack works while prod stays `Secure` behind TLS.

### 🟠 HIGH — Backgrounded-task SSE subscriber dies at connect and never restarts — *code-analysis*
- **Where:** `backend/app/services/events.py:301-303`; guard at `backend/app/routers/events.py:77`.
- **What:** `run_task_subscriber` returns immediately when `conversation_id` is empty. The frontend opens `GET /api/events` during bootstrap *before* `POST /api/sessions` sets `conversation_id`, so the subscriber exits; the `get_task_subscriber(sid) is None` guard then prevents any restart for the connection's lifetime. Result: `task_progress`/`task_done` are **never delivered** for a backgrounded turn on that session — the UI spins forever and the answer is lost. Parity regression (Chainlit started this notifier in `on_chat_start`, after the conversation existed).
- **Recommended fix:** change the guard to `is None or task.done()` (restart a dead subscriber), or have `run_task_subscriber` await until `session.conversation_id` is set before subscribing.

### 🟠 HIGH — Fast-finishing backgrounded `task_done` dropped by the frontend gate — *code-analysis*
- **Where:** `frontend/src/lib/store/chat.ts:283` (gate) and `:218` (id registered only after POST resolves); backend publishes during POST via `reconcile_backgrounded` (`backend/app/routers/chat.py:150-161`).
- **What:** for a task that finishes almost immediately, the SSE `task_done` frame can arrive before `applyResponse` adds the `task_id` to `awaitedTaskIds`. The `onTaskDone` gate early-returns and discards the completion (including its `response`); a `done:false` backgrounded ToolItem is then created and never finalized → stuck "Running in the background…", answer never appended. This defeats the very fast-finish (T-4) case the backend `reconcile` was added to handle.
- **Recommended fix:** buffer early `task_progress`/`task_done` events by `task_id` and drain them in `applyResponse`'s backgrounded branch immediately after `awaitedTaskIds.add(...)`.

### 🟡 MEDIUM — Task subscriber never resubscribes after a transient Redis error — *code-analysis*
- **Where:** `backend/app/services/events.py:325`.
- **What:** a mid-stream Redis/pub-sub reset raises inside the `listen()` loop; the handler logs and returns, leaving a dead-but-registered subscriber. The SSE transport stays up (so the browser never reconnects) and background events are **silently dropped** until the tab is reloaded. The Redis client is built with zero retries (`from_url` bypasses the default retry policy).
- **Recommended fix:** wrap the subscribe loop in a reconnect/backoff loop, and/or treat a `.done()` subscriber task as absent so a new connection restarts it.

### 🟡 MEDIUM — `auto_approve` plan flips `awaiting` to `false` during execution — *code-analysis; gated*
- **Where:** `frontend/src/lib/store/chat.ts:198-199` (auto-approve fires nested `decidePlan`) vs `:338-340` (outer `post`'s `finally`).
- **What:** only when `auto_approve_steps` is enabled (off by default). The nested approval POST sets `awaiting=true`, then the outer POST's `finally` synchronously sets it back to `false`, so the composer is re-enabled and the in-flight indicator lost while the plan is still executing; pressing Enter can fire a competing concurrent turn.
- **Recommended fix:** use an in-flight counter instead of a boolean, or defer the auto-approve `decidePlan` until after the outer post settles.

### 🟢 LOW — Late status frame after terminal response → orphan spinner — *plausible (narrow race)*
`frontend/src/lib/store/chat.ts:257` — `onStatus`'s create-branch makes a `done:false` ToolItem with no guard against an already-finalized turn. Fix: track finalized `turn_id`s and skip creation for them.

### 🟢 LOW — Element dedup can drop distinct same-named artifacts — *plausible*
`frontend/src/lib/chainlit/elementDeduplication.ts:24` — `resourceSignature` reads `props.name` before the stamped `artifact_id`, so two distinct json/thermal/reference artifacts sharing a name collapse to one (the `artifact_id` stamp at `artifactAdapter.ts` is defeated). Reachable trigger (same material + same skill twice in a turn) is unproven. Fix: fold `artifact_id`/`element.id` into the signature unconditionally for custom elements.

### 🟢 LOW — Follow-up submission sends the needs_info *prompt text* as the user query — *confirmed*
`frontend/src/lib/store/chat.ts:359-366` — `submitFollowup` sets `query = it.message` (the assistant's prompt) and POSTs it with `followup_answers`. The client-agent records that as a `role:"user"` history turn, polluting downstream reasoning. `backend/CONTRACT.md`'s follow-up example expects the original query resent. Fix: send `query:""` (like plan approval) or store and resend the original user query.

### ✅ FIXED — `CONTRACT.md` CSV self-contradiction — *doc-only*
`backend/CONTRACT.md` prose said `text/csv` → `json`, but the authoritative table (same section) + the classifier (`services/artifacts.py`) + tests (`test_contract_matrix.py`) all say `file`. **Corrected the prose in this review** (zero-risk documentation change; the actual `json` fold is the `data` *tag*).

---

## Investigated and dismissed

- **Bug-hunt's "blocker" — "A2A `kind` discriminator breaks every chat turn" — FALSE POSITIVE.** The finder reproduced it by feeding a stock `a2a-sdk` `TextPart` shape (`{"kind":"text","text":…}`) straight into `A2AClient._parse_response`, bypassing `consume_stream_response`. In reality the `prometheus_api` base image uses bare A2A-v1 parts — its docstring states *"root-wrapped parts … are intentionally not supported,"* and its own `extract_status_message_text` uses the same allowlist (rejecting `kind`) as `backend/app/a2a_client.py:196`. The client-agent emits `{"text": …}` parts, the backend parser matches, and **a live chat turn completed successfully with a proper report.** *Residual (low-risk):* verified against base image `containers.github.inl.gov/genesis/prometheus_api:latest` (`54d617e7f492`); worth a re-confirm against the pinned `88e920d` when on VPN.
- **"Per-step plan status no longer derived from SSE" — not a regression.** Documented, accepted deferral (`tasks/remediation/02-chat-turn.md`, T-16); the live `ToolStep` still shows running/finished status lines from the SSE `status`/`history` stream.

---

## Accepted follow-ups

Pre-accepted by the branch owner as out of scope for this PR (flagged, untouched):

- **Interactive Exodus/STL mesh → plain download** (no backend VTK→VTP pipeline) — largest parity regression.
- **Conversation-history UI absent** — `GET /api/conversations/recent` + client method exist; `LeftPanel` is a placeholder (React cutover Step 08).
- **Chainlit/recoil residue** — `@chainlit/react-client` + `recoil` in `frontend/package.json`, `main.tsx` providers, dead `frontend/src/lib/chainlit/chainlit.ts`, `DynamicFormElement`'s `askUserState`, stale `VITE_CHAINLIT_SERVER` in `vite.config.ts` + `docker-compose.yml`, dead JSX in `frontend/public/elements/` (React cutover Step 09).
- **Stale `.env.example` entries** — `OAUTH_OKTA_*`, `CHAINLIT_URL` (unused).
- **Deferred-acceptable backend items** — SSE replay / `Last-Event-ID` (E-4), password hashing at rest (AU-3, dev-only plaintext), in-memory session/revocation state lost on restart, OAuth callback 501 seam, no server-side task cancel.
- **Doc nit** — `CLAUDE.md:13` calls `@chainlit/react-client` a "kept adapter"; the kept adapter is actually the type-only `frontend/src/lib/chainlit/*.ts` modules.

---

## Observations & housekeeping

- **The real bugs cluster in the backgrounded-task / SSE-late-event path** — the least unit-tested corner (existing tests seed `conversation_id` and use fake subscribers that never exit). If the backgrounded path is kept, it deserves a targeted test plus the HIGH/MEDIUM fixes above. These findings are high-confidence code analysis but were **not** live-triggered (the simple smoke query completed synchronously).
- **Stale local `backend/.venv`:** after the `chat-backend/` → `backend/` rename, the venv's console-script shebangs still point at the old `chat-backend/.venv/bin/python3`, so `uv run … pytest`/`mypy` fail with *"Failed to spawn."* Invoke the venv Python directly instead: `./.venv/bin/python -m pytest`. This is a gitignored local artifact, **not** a branch defect (CI recreates the venv fresh).
- **Live-run image note:** the pinned base image `containers.github.inl.gov/genesis/prometheus_api:88e920d` (Makefile default) requires INL VPN/registry access. The live run here used `PROMETHEUS_API_BASE_IMAGE_HASH=latest` against the locally-present `:latest` base image. `make up` also cleared the LiteLLM Postgres volume (its normal behavior).
