# 10 — Verification: status-matrix harness + contract test

## Goal

Prove the backend is correct end-to-end **without** the React app: an httpx/curl harness that
exercises every status path, plus a pytest that asserts we handle every `ConversationStatus`.

## Files to create

- `backend/scripts/smoke.py` (or `.sh`) — end-to-end harness against a running stack.
- `backend/tests/test_contract_matrix.py` — status coverage test.
- `backend/tests/test_*.py` — per-router unit tests (auth, chat mapping, uploads,
  artifacts classification, events).

## Harness (`scripts/smoke.py`) — against a running client-agent + redis + backend

1. `POST /api/auth/login` (`prometheus/prometheus`) → capture cookie.
2. `GET /api/auth/me` → 200.
3. `POST /api/sessions` → `conversation_id`.
4. Open `GET /api/events` (SSE) in a background task; collect frames.
5. `POST /api/chat/messages` with a **simple query** → assert `completed` (+ any artifacts);
   assert `status` frames arrived on SSE with the matching `turn_id`.
6. **needs_info**: a query that triggers follow-up → `needs_info` with `followup_questions`;
   POST again with `followup_answers` → progresses.
7. **plan_ready**: a plan query → `plan_ready` with `plan` + `auto_approve`; POST
   `plan_approved: true` → executes; separately test `plan_rejected: true`.
8. **backgrounded**: a slow query → `backgrounded` with `task_id`; assert a `task_done` frame
   arrives on SSE carrying the mapped response.
9. **upload**: `POST /api/uploads` → descriptor; reference `upload_id` in a chat message.
10. **artifact content**: for a completed turn's artifact, `GET /api/artifacts/{id}/content`
    → correct bytes + MIME.
11. **history**: `GET /api/conversations/recent` → list.

Print PASS/FAIL per path. If the client-agent can't easily produce a given status, publish
synthetic Redis events (task 05 approach) to exercise the background path deterministically.

## Contract test (`tests/test_contract_matrix.py`)

- Mirror `tests/infrastructure/test_contract_static.py:277` ("handles every
  `ConversationStatus.values()`"): for each status value, feed a canned `ConversationResponse`
  payload through the chat service's `map_response()` and assert it produces a valid
  `ChatMessageResponse` with the right shape (no unhandled status falls through to a 500).
- Unit-test `to_artifact_meta` `render_hint` classification across the artifact types in
  `docs/docs/dev-docs/artifacts.md` (pdf/data/report/file/ifc/exodus/stl/mermaid/reference/
  thermal/unknown).
- Unit-test `normalize_followup_questions` against the raw question shapes handled in
  `_handle_needs_info`.

## Acceptance check

- `uv run pytest` green in `backend/tests/`.
- `scripts/smoke.py` reports PASS for every status path against a live stack.
- ~~The old Chainlit app still builds and runs (regression check — it was untouched).~~
  *(No longer applicable — the Chainlit `frontend` app was removed on this branch.)*

## Wrap-up

- Update `frontend/AGENT-CONTRACT.md` to point at the new `backend/CONTRACT.md`
  (task 01) as the source of truth for the new API; note the Chainlit element contract is
  legacy.
- Confirm no `chainlit` import exists anywhere under `backend/`.
