# 05 — SSE events channel + background-task delivery

## Goal

One long-lived SSE stream per session (`GET /api/events`) carrying `status`,
`task_progress`, and `task_done` events. This replaces Chainlit's `cl.Step` live updates and
the out-of-band `run_task_notifier`. Decision **D2**.

## Files to create

- `chat-backend/app/services/events.py`
- `chat-backend/app/routers/events.py`

## `services/events.py` — event bus + Redis subscriber

### In-process event bus
- Per-session `asyncio.Queue` registry keyed by `sid`. `publish(sid, event)` and an async
  `subscribe(sid)` generator the SSE endpoint drains.
- The chat turn's `on_status` (task 04) calls `publish(sid, StatusEvent(turn_id, message))`.

### Redis subscriber — port `run_task_notifier` (message_handler.py:432)
- One `task_events.subscribe(redis_url, conversation_id)` loop per active SSE stream, started
  when the stream opens, cancelled on disconnect. (Chainlit started it in `on_chat_start`
  bound to the ws context; here it's owned by the SSE connection lifetime.)
- **Root-vs-child filtering** (message_handler.py:457): only act on events where
  `task_id == root_task_id` and `root_task_id in session.awaited_task_ids`. Ignore sub-node
  noise.
- Terminal state → port `_maybe_announce_completion` (message_handler.py:403):
  - Idempotent via the awaited-ids set — first consumer wins; discard the id after.
  - Non-`completed` terminal → `TaskDoneEvent(task_id, state, response=None)` + a message.
  - `completed` → `task_events.fetch_result(...)`, run it through task 04's `map_response`
    (via `response_from_payload`), emit `TaskDoneEvent(task_id, "completed", response=<mapped>)`.
- Non-terminal → `TaskProgressEvent(task_id, message)`.

### Fast-finish guard
- Port from `_handle_backgrounded` (message_handler.py:389): when a turn returns
  `backgrounded`, task 04 registers the id; here, on stream open (or when the id is first
  registered), check `task_events.node_snapshot`; if already terminal, announce immediately so
  we don't miss the event that fired before subscribe. Preserve the "consume the awaited id
  once" semantics so the guard and the subscriber can't double-announce.

### Progress history
- Keep the `BACKGROUND_STATUS_HISTORY_LIMIT = 50` cap when accumulating progress messages for
  a task, if we surface history in `TaskProgressEvent`.

## `routers/events.py`

- `GET /api/events` — auth required. Returns `StreamingResponse` with
  `media_type="text/event-stream"`. Emits SSE frames (`event:`/`data:` lines) for each queued
  event, plus a periodic heartbeat comment (`: ping\n\n`) to keep the connection alive.
  Start the Redis subscriber task on connect; cancel on disconnect (client gone).

## Acceptance check

- Open `GET /api/events`, then `POST /api/chat/messages`; assert `status` frames arrive
  during the turn carrying the same `turn_id` as the POST response.
- Trigger a backgrounded turn; assert a `task_done` frame arrives with the mapped response
  after the task completes (publish a synthetic terminal event on
  `tasks:events:{cid}` + a result at `tasks:result:{cid}:{tid}` to test without a slow agent).
- Fast-finish: pre-seed a terminal node snapshot, register the id, open the stream → a
  `task_done` fires once (not twice).
- SSE survives idle via heartbeats; disconnect cancels the subscriber (no leak).

## Infra note

- uvicorn/nginx must not buffer this route: `proxy_buffering off`, long `proxy_read_timeout`
  (task 09).
