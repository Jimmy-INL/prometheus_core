# 03 — SSE events + background-task notification fixes

**Findings:** T-4 `[REG]` (High), T-5 `[REG]` (High), E-1 `[REG]`, E-2 `[REG]`, E-3 `[GAP]`, E-5 `[REG]`.
**Depends on:** 01. **Verify:** `test_events.py` + new cases green.
**Status:** ✅ Implemented (app/services/events.py, app/routers/events.py, app/routers/chat.py, app/contract.py, CONTRACT.md; tests in test_events.py). T-5 = one subscriber per sid (bus tracks it; router starts on first connection, cancels on last). T-4 = `reconcile_backgrounded()` re-checks the node after a turn backgrounds, gated on an active listener. E-2 = `_announce_completion` claims the awaited id up front but restores it on failure/cancel. E-1 = `_make_on_status` accumulates deduped/capped history. E-3 = bounded queue (drop-oldest). E-5 = `TaskDoneEvent.message` for non-completed states. **E-4 (SSE replay / `Last-Event-ID`) deliberately deferred** — noted as a known gap.

The Redis channel-naming, message shape, and root-vs-child filter were ported faithfully;
the bugs are all in *where/when* the ported logic runs after moving from one-notifier-per-
websocket to one-subscriber-per-SSE-connection over a session shared across tabs.

## T-4 — Fast-finish race: a quickly-finishing backgrounded task is missed (High)

The fast-finish guard moved from the backgrounding POST (`message_handler.py:384`) to
SSE-subscriber connect time (`services/events.py:211`). If a task hits a terminal Redis
event between the connect-time snapshot and `_map_backgrounded` registering the id
(`services/chat.py:157`), the live loop skips it (`events.py:222`) and nothing re-checks.
Fix: after `_map_backgrounded` adds the id to `session.awaited_task_ids`, re-run the node
snapshot check for that id (port the per-POST `node_snapshot` recovery), publishing
`task_done` if it already finished. Test: task finishes before the subscriber sees it →
`task_done` still delivered.

## T-5 — One subscriber per session, not per connection (High)

`routers/events.py:72` starts a fresh `run_task_subscriber` per `/api/events` connection;
two tabs of one login `sid` → two subscribers on the same `tasks:events:{conversation_id}`
channel → duplicated `task_progress` (E-3-adjacent). Fix: hoist the subscriber to
per-session (keyed by `sid`/conversation) with reference counting across connections, or a
single subscriber whose output fans out through the existing `EventBus` to all of the
session's queues (dedup once, centrally). Ensure clean teardown when the last connection
for a session closes. Test: two simultaneous queues for one `sid` receive each
`task_progress` exactly once.

## E-1 — Populate `StatusEvent.history` (Medium)

Contract declares `history` (`contract.py:275`) but `_make_on_status`
(`routers/chat.py:60`) always emits `history=None`. Old accumulated a de-duplicated,
numbered running list (`message_handler.py:121-143`). Fix: keep per-turn status history
(suppress consecutive duplicates) and include it in each `StatusEvent`. Reuse the 50-line
cap already applied to background progress. Test: three status callbacks → the third event
carries the accumulated de-duplicated history.

## E-2 — Don't discard the awaited id before the result is fetched (Medium)

`events.py:109` discards the id, then awaits `fetch_result` (`:118`); a disconnect during
that await cancels the task with the id already consumed → `task_done` never delivered.
Fix: fetch/publish first, discard the id only after a successful publish (or make the
discard idempotent + recoverable on reconnect). Test: cancel mid-fetch → a reconnecting
subscriber still delivers `task_done`.

## E-3 — Bound the per-connection event queue (Low/GAP)

`events.py:65` `asyncio.Queue()` has no `maxsize`; a stalled tab grows it unbounded. Fix:
give it a sane `maxsize` and drop-oldest (or coalesce progress) on overflow, logging when
it happens. Test: overflow drops rather than grows without bound.

## E-5 — Preserve human-readable text for non-`completed` terminal states (Low)

Failed/canceled/rejected emit `TaskDoneEvent(response=None)` (`events.py:111`); old posted
`"⚠️ Background task ended ({state})."` (`message_handler.py:420`). Fix: include a
human-readable `message` (or a minimal response) for terminal non-completed states so the
frontend has something to render.

## Not here

E-4 (SSE replay / `Last-Event-ID`) — defer; note in code as a known gap. The heartbeat
framing (`: ping`) and cookie auth on `/api/events` are already correct; the frontend must
open the stream with `withCredentials` (a Bucket A note).

## Verify

`cd chat-backend && uv run pytest tests/test_events.py && uv run ruff check && uv run mypy app/`.
