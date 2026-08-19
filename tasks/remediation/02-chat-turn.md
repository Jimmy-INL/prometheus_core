# 02 — Chat-turn orchestration fixes

**Findings:** T-1 `[REG]`, T-2 `[REG]`, T-7 `[REG]`, T-8 `[REG]`, T-11..16 `[REG/minor]`.
**Depends on:** 01. **Verify:** `test_chat_turn.py` + new cases green.
**Status:** ✅ Implemented (chat-backend/app/routers/chat.py, app/services/chat.py, app/sessions.py; tests in test_chat_turn.py). T-1/T-2/T-7/T-8 fixed in the backend. **T-11/T-12/T-15/T-16 deliberately left to the frontend** (pure presentation, or an intentional new-UX change): the new contract keeps `needs_info` as `needs_info` even with zero questions (a contract test asserts this), the `**Error:**` prefix and per-step plan-status are render concerns, and the dropped `/tasks` hint is correct for the SSE-delivered UX. These are recorded as "Presentation parity notes" in `../frontend/README.md`.

## T-1 — Uploads-only turn is rejected (High)

`routers/chat.py:86` guards on query/followup/plan flags but **not** `body.upload_ids`, so
a file with no caption → 422; the old neutral default query is also gone. Fix:
1. Include `body.upload_ids` in the "has something to do" guard.
2. When there's no query but there are uploads, default `query` to the old text
   `"Please process the uploaded file(s)."` (`message_handler.py:227`) before dispatch.
Test: a request with only `upload_ids` reaches `handle_turn` with the default query.

## T-2 — Follow-up depth cap dropped (High)

Old capped consecutive `needs_info` at 5 (`_MAX_NEEDS_INFO_DEPTH`, `message_handler.py:262,492`).
The new service dropped it "to the frontend," but it exists nowhere. Decision for this
pass: **re-add a lightweight server-side counter** in `SessionState` (e.g.
`consecutive_needs_info: int`), incremented when a turn returns `needs_info` and reset on
any other terminal status; when it exceeds the cap, return a normal message ("Too many
consecutive follow-up requests.") instead of another `needs_info`. This is robust
regardless of frontend behavior; the frontend may still add its own UX guard. Test: a stub
agent that always returns `needs_info` terminates after the cap.

## T-7 — `artifacts=[]` wipes the session catalog (Medium)

`services/chat.py:122` `if response.artifacts is not None:` overwrites `session.artifacts`
with `[]` on an empty-list turn (old used truthy, `message_handler.py:679`), breaking later
`GET /api/artifacts/{id}/content`. Fix: `if response.artifacts:` (truthy). Test: a turn
with `artifacts=[]` preserves a previously-populated `session.artifacts`.

## T-8 — Overlapping `report`/`response_text`/`message` (Medium)

`_map_final` (`chat.py:130-138`) sets all three; for `answer` `report == response_text`,
and a short `message` the old code suppressed now leaks. Fix: emit a single authoritative
text field per status (old precedence `report → response_text → message`, first non-empty),
and null the others so a frontend can't double-render. Update `CONTRACT.md`'s
`completed`/`answer`/`recommendation` examples to match. Test: `answer` yields
`response_text` set and `report`/`message` null (or the agreed single-field shape).

## T-11..16 — Minor behavior regressions (Low; batch)

- **T-10-ish/T-12** empty-question `needs_info` should degrade to a plain message
  (`chat.py:64`) as old did (`message_handler.py:496`), so a frontend awaiting a form
  doesn't hang on zero fields.
- **T-11** restore the `**Error:**` markdown prefix on `error` (`chat.py:202`) — or
  confirm the frontend adds it; pick one.
- **T-15** backgrounded default message: restore the "(use /tasks to check progress)" hint
  or intentionally drop (cosmetic; align with whatever the frontend shows).
- **T-13/T-14** select-option reconstruction dropping extra keys (`contract.py:118`) and
  empty-string key fallback semantics (`contract.py:130`): low-risk; leave as-is unless a
  test surfaces breakage — note in code comments.
- **T-16** live per-step plan-status heuristic (`_update_step_statuses`) is rendering-scope
  → defer to the frontend cutover (Bucket A); note only.

(Related **T-9/T-10 auto-approve/reject round-trips** are correctly threaded on the
backend; their behavior lives in the frontend cutover — not fixed here.)

## Verify

`cd chat-backend && uv run pytest tests/test_chat_turn.py && uv run ruff check && uv run mypy app/`.
