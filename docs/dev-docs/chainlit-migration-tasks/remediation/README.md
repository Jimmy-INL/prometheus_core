# Tasks — Migration remediation (backend correctness + deployment + hardening)

Follow-on to the backend build (`../README.md`, steps 00–10 done) and companion to the
React cutover (`../frontend/README.md`). A pre-release parity/bug audit compared the old
Chainlit `frontend/` (source of truth — since **removed** on this branch; recover from git
history) against the new `backend/` + `frontend/` and surfaced ~50 findings. Full report +
evidence: the approved plan `~/.claude/plans/smooth-snuggling-bumblebee.md`.

## Verdict

> **Updated (branch `old-frontend-removal`):** the verdict below was the *audit-time* snapshot.
> Since then — **Bucket B (this dir) is complete**; the **React cutover is well underway**
> (`../frontend/README.md` steps 00–05 + 07 done, 06 partial, 08/09 remain), so the app is no
> longer a 100% Chainlit client; and the **prod blockers are resolved** — the JWT secret is now
> delivered + fail-fast (step 00) and nginx already proxies `→ backend:8000` (no
> `chainlit-frontend` upstream; that service was removed).

*Audit-time snapshot (historical):* the **backend was largely built and faithful**; the **React
cutover had not started** (the app was still a 100% Chainlit websocket client — Bucket A); and the
**stack couldn't run in prod** as-configured (nginx pointed at a `chainlit-frontend` upstream; the
backend JWT secret never reached the container). Under those blockers sat real backend regressions
(SSE background-task races, an uploads-only turn that 422s, a session artifact catalog that gets
wiped, a strict form-field type that errors whole turns) plus a hardening backlog.

**Verified correct (no action):** `uri_resolver` is byte-identical (schemes + DeepLynx
auth preserved); upload size/MIME/staging is a faithful port; content-proxy streaming
mechanics are sound; `config.yml` keys match; cookie flags are correct; `conversation_id`
is server-side (no session fixation); base-contract fields are almost all represented.

## Two buckets

- **Bucket A — the React cutover.** Fully planned in
  [`../frontend/README.md`](../frontend/README.md) as an ordered 9-step effort (transport,
  SSE, `ChatStatus` handling, `render_hint`→viewer adapter, auth/session/config/upload
  endpoints); steps 00–05 + 07 are done, 06 partial, 08/09 remain. Not re-planned here. Its
  Step 09 owns the remaining Vite proxy cleanup (`VITE_CHAINLIT_SERVER` + legacy routes); the
  nginx fix (BLK-2) is **already done** (`→ backend:8000`).
- **Bucket B — this directory.** Everything the *frozen contract* and *deployment* need to
  be correct **before/while** Bucket A happens. `../frontend/README.md` explicitly assumes
  the contract is frozen-and-correct — these fixes make that true.

## Tags

`[REG]` migration regression · `[GAP]` new-design work incomplete · `[CARRY]` pre-existing
weakness ported from Chainlit · `[DOC]` contract/doc inconsistency.

## Step order (Bucket B)

| # | File | Summary | Findings | Status |
|---|------|---------|----------|--------|
| 00 | `00-deployment-blocker.md` | Deliver + fail-fast JWT secret; Redis URL/password consistency | BLK-3, DEP-1 | ✅ Done |
| 01 | `01-contract-correctness.md` | One authoritative `render_hint` enum; loosen `input_type`; citation `metadata`; markdown report | DOC-1, T-3/A2, CON-1, A-1 | ✅ Done |
| 02 | `02-chat-turn.md` | Uploads-only turn; depth cap; artifacts-`[]` wipe; overlapping text fields; minors | T-1, T-2, T-7, T-8, T-11..16 | ✅ Done |
| 03 | `03-events-sse.md` | Fast-finish race; per-session subscriber; `history`; discard-before-fetch; bounded queue; terminal text | T-4, T-5, E-1, E-2, E-3, E-5 | ✅ Done |
| 04 | `04-artifacts-uploads.md` | Upload MIME refinement; tag-vs-MIME precedence; cache eviction; empty id; Content-Disposition; graceful 502; CSV | T-6, A-2, A-3, A-4, A-5/6, A-7, A-9 | ✅ Done |
| 05 | `05-hardening.md` | Password hashing; logout revocation; history sort; config auth; conn reuse; profile validation; CORS; OAuth | AU-1/2/3/5/6/7/8/9 | ✅ Done |

Out of Bucket B (owned elsewhere): **BLK-1** (React cutover) + **BLK-4** (Vite `/api` proxy
repoint) → `../frontend/README.md`; **BLK-2** (nginx) is **done** (`→ backend:8000`).
**T-9/T-10** (auto-approve/reject round-trips) get their home in the frontend cutover but the
backend already threads the flags correctly.

## Progress log / handoff

_Branch `old-frontend-removal`. **Bucket B (steps 00–05) is COMPLETE and unit-verified**
(174 passing, ruff + mypy clean). Not yet exercised via a live `make up` (no Docker run
in-session). **Bucket A (the React cutover in [`../frontend/README.md`]) is now well underway** —
steps 00–05 + 07 done, 06 partial, 08/09 remain; it codes against the corrected contract._

### Environment notes (read before running anything)
- `backend/` **and** `tasks/` are now **git-tracked** on this branch (they were untracked when
  Bucket B first landed; they've since been committed), so `git log`/`git diff` show the history.
  This file + the code comments remain a good narrative record of what changed.
- **Tests need `--offline --no-sync`**: `uv run pytest` tries to re-fetch the internal
  `prometheus-api` git dependency and fails without network/VPN auth. The existing
  `.venv` already has it, so run:
  `cd backend && uv run --offline --no-sync pytest -q` (same for `ruff check` / `mypy app/`).
- Baseline before this work: 133 passed. After steps 00–01: **144 passed**, ruff + mypy clean.

### ✅ Step 00 — deployment blocker (BLK-3, DEP-1)
- `docker-compose.yml` — `backend` service now forwards `CHAINLIT_AUTH_SECRET`
  (the documented JWT fallback that previously never reached the container).
- `backend/app/main.py` — lifespan raises a clear `RuntimeError` on an empty
  `jwt_secret` (fail on boot, not a 500 at first login). Safe for tests: they build a bare
  `TestClient(app)` which does **not** run the lifespan.
- `backend/app/config.py` — new `_redis_url()` folds `REDIS_PASSWORD` into a
  credential-less `REDIS_URL` (URL-encoded), closing the `NOAUTH` footgun; no-op for the
  documented `.env` form that already embeds the password.
- `.env.example` — clarified that one of `BACKEND_JWT_SECRET` / `CHAINLIT_AUTH_SECRET`
  must be non-empty.
- Tests: `backend/tests/test_config.py` (new) — 4 Redis cases + 2 lifespan cases.

### ✅ Step 01 — contract correctness (DOC-1, T-3, CON-1, A-1)
- `backend/app/contract.py` — `RenderHint` is now the single source of truth (added
  `report`); `_coerce_input_type()` maps unknown/empty follow-up field types → `text`;
  new `Citation{source,section,page}` sub-model + `ArtifactMeta.citation` field.
- `backend/app/services/artifacts.py` — `text/markdown` / `text/plain` / `.md` now
  classify as `report` (was `file`); `_citation_from()` lifts citation metadata onto the wire.
- `backend/CONTRACT.md` — render-hint table rewritten to mirror the enum exactly (+ a
  `citation` example); `test_contract_matrix.py::test_every_render_hint_value_is_reachable`
  guards against future drift.
- Tests: extended `test_artifacts.py` (report + citation cases) and `test_contract_matrix.py`
  (markdown→report row, unknown-input_type→text case).

**Three contract decisions baked in (flag if the frontend team disagrees before building):**
1. Added `report` to the enum; markdown/plain render inline again (the frontend adapter needs
   a markdown path for `report` — trivial, `react-markdown` is already a dep).
2. Kept `svg` folded into `image` and `json` (not `data`) — no separate viewers added.
3. `Citation` is a typed sub-model (source/section/page only); widen it if agents emit more.

### ✅ Step 02 — chat-turn
T-1 uploads-only turn (default query, no 422), T-2 follow-up depth cap (`SessionState`
counter), T-7 `artifacts=[]` no longer wipes the catalog, T-8 one authoritative text field
per terminal status. T-11/12/15/16 left to the frontend (presentation / intentional UX).

### ✅ Step 03 — events-SSE
T-5 one subscriber per session (bus-tracked; started on first connection, cancelled on last),
T-4 `reconcile_backgrounded` fast-finish recovery, E-1 accumulated status `history`, E-2
awaited-id restored on failure/cancel, E-3 bounded event queue, E-5 `TaskDoneEvent.message`
for non-completed states. E-4 (SSE replay) deferred.

### ✅ Step 04 — artifacts / uploads
T-6 exodus container MIMEs, A-2 classifier reorder (specific MIME > tags > generic MIME),
A-3 per-request temp dir + cleanup, A-4 `artifact_identity` for id-less artifacts, A-5/A-6
disposition + RFC 5987 filename, A-9 CSV → file. A-7/A-8 left to the frontend.

### ✅ Step 05 — hardening
AU-1 logout revocation, AU-2 sort-before-slice, AU-3 constant-time compare (hashed-at-rest
deferred), AU-5 `/api/config` auth, AU-6 provider registry seam, AU-7 client reuse, AU-8
profile validation, AU-9 explicit dev CORS.

### ▶ Resume here — finish Bucket A (React cutover)
Bucket B is done and Bucket A is well underway ([`../frontend/README.md`] steps 00–05 + 07 done).
Remaining cutover work: **finish 06** (drop the recoil dependency in `DynamicFormElement`),
**08** (wire or defer history), and **09** (excise the leftover Chainlit/recoil client code +
vite/compose proxies). The contract is corrected (note the `report` hint + `ArtifactMeta.citation`,
and the "Presentation parity notes" in the frontend doc for `needs_info`-empty / error styling /
per-step plan status / gif-webp / content-fetch-failure). Full evidence is in the approved plan
`~/.claude/plans/smooth-snuggling-bumblebee.md`. Neither bucket has yet been validated by a live
`make up` — do that (see step 00 verify) with the cutover.

## Ground rules

- **Additive + non-breaking (backend contract).** Changes are testable against the running
  backend (host `:8600`). No wire-shape change without updating `backend/CONTRACT.md` +
  `app/contract.py` + the contract tests together. *(The Chainlit stack no longer runs — it was
  removed on this branch.)*
- After each step: `cd backend && uv run pytest && uv run ruff check && uv run mypy app/`.
- Extend the existing suites (`tests/test_chat_turn.py`, `test_events.py`,
  `test_artifacts.py`, `test_contract_matrix.py`) rather than adding parallel ones.
