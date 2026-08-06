# Background / Long-Running Tasks — Implementation Reference

Status: **Phase 0 + Phase 1 (turn-level backgrounding) implemented and wired end-to-end, gated OFF by default.**
Companion to the design doc [`background-tasks.md`](./background-tasks.md), which holds the *why*, the
full data model, the percolation algorithm, and the phasing. This document is the **as-built** reference:
what exists in the tree today, how the pieces connect, and exactly what is left to finish Phase 1.

For background on *why* LiteLLM constrains the design (only `message/send` and `message/stream` are
forwarded), see the design doc's "LiteLLM readiness assessment".

---

## TL;DR

A user turn that takes too long no longer blocks the user. The client-agent races the orchestration
against a soft deadline; if the deadline fires it **detaches** the work into a background `asyncio.Task`,
returns a `backgrounded` response immediately, and the user regains input control. The detached task keeps
running, finalizes its node in the per-conversation **Task Graph**, and persists its final payload to Redis.
The frontend, on receiving `backgrounded`, spawns an in-session watcher that subscribes to the Task Graph's
Redis pub/sub channel, updates one live status Step as work progresses, and renders the result out-of-band
when the task completes.

There are **two detach triggers**:

1. **Time-based auto-promotion** — gated by `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` (default `0` = off).
   When `> 0`, any turn still running past the deadline detaches. This is the "ships dark" switch.
2. **Agent-driven (`declare_long_running`)** — an agent that *knows* it will be slow calls
   `self.declare_long_running(...)` near the start of its skill, which the orchestrator turns into an
   *immediate* detach. **Always active**, independent of the deadline — it's opt-in per agent, so only
   agents that explicitly declare (today: just the thread-pattern debug agent's `run_background_task`)
   ever background. A turn with neither trigger active runs exactly the synchronous path.

---

## `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS`

The single switch that controls backgrounding.

| | |
|---|---|
| **Where read** | `agents/client-agent/orchestrator/task_tracking.py` → `background_deadline_seconds()` |
| **Where used** | `agents/client-agent/orchestrator/service.py` → `_execute()` (around line 533) |
| **Type / units** | Float, **seconds**. Parsed leniently: empty/unset/non-numeric → `0.0`; negatives clamped to `0.0`. |
| **Default** | `0` |
| **Meaning** | The **soft deadline** for a single user turn. The orchestrator runs `chat()` as a task and waits up to this many seconds. If `chat()` finishes first, the turn returns synchronously as before. If the deadline fires first, the turn is **detached** to the background and the user gets a `backgrounded` response. |
| **`<= 0` (default)** | **Backgrounding disabled.** `_execute()` takes an early-return branch that awaits `chat()` directly — the original synchronous behavior, with no `asyncio.wait`, no detach, no `backgrounded` status ever produced. |
| **`> 0`** | Backgrounding active. E.g. `45` = "anything still running 45 s into the turn detaches and finishes in the background." |

```python
# task_tracking.py
def background_deadline_seconds() -> float:
    raw = os.getenv("PROMETHEUS_BACKGROUND_DEADLINE_SECONDS", "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0
```

```python
# service._execute()  (abridged)
deadline = task_tracking.background_deadline_seconds()
if deadline <= 0:
    response = await _run_chat()                       # synchronous path, unchanged
    task_tracking.finish_turn(response.status)
    return self._response_payload_with_artifacts(...)

chat_task = asyncio.create_task(_run_chat())
bg_evt = task_tracking.background_event()              # agent-driven detach signal (declare_long_running)
waiters = {chat_task} | ({asyncio.create_task(bg_evt.wait())} if bg_evt else set())
done, _ = await asyncio.wait(waiters, timeout=deadline if deadline > 0 else None,
                             return_when=asyncio.FIRST_COMPLETED)
if chat_task in done:
    response = chat_task.result()                      # finished before any detach trigger → return normally
    ...
else:
    root_id = task_tracking.ensure_background_root()   # deadline OR background signal → detach
    self._spawn_background_finisher(chat_task, ...)
    return ConversationResponse(status="backgrounded", message_metadata={"task_id": root_id}, ...)
```

> **Why the deadline defaults off:** time-based auto-promotion is sequenced to land after the frontend and
> base-image pieces. Until you've validated the end-to-end flow against a real slow agent, leaving the
> deadline at `0` keeps production on the proven synchronous path *for ordinary turns*. Flip it on (per
> environment, e.g. `45`) after the smoke test. Note the agent-driven path (`declare_long_running`) is
> **not** gated by this — but it only fires for agents that explicitly opt in.

Related env vars:

| Var | Default | Effect |
|---|---|---|
| `TASK_NODE_TTL` | `86400` (24 h) | TTL (seconds) for Task Graph nodes, the roots list, and stored results in Redis. Refreshed on every write. |
| `PROMETHEUS_TASK_STORE` | unset (Redis) | `memory` forces the SDK's volatile `InMemoryTaskStore` instead of `RedisTaskStore` (Layer A; base-image only — see below). |

---

## File map (what lives where)

| File | Layer | Role | Base-image? |
|---|---|---|---|
| `agents/client-agent/task_graph.py` | B (Task Graph) | `TaskNode` model, Redis CRUD, `reconcile()` percolation, pub/sub `_publish_event`, `store_result`/`get_result`. | No |
| `agents/client-agent/orchestrator/task_tracking.py` | B | Turn/skill → graph integration: `begin_turn`/`finish_turn`, lazy root, `track_skill` ctx manager, `background_deadline_seconds`, `ensure_background_root`, `run_background_finish`, **`background_event`/`request_background`** (proactive detach signal). | No |
| `agents/client-agent/orchestrator/service.py` | B | `_execute()` races `chat()` against the deadline **and** the background event; `_spawn_background_finisher`; builds the `backgrounded` response. | No |
| `agents/client-agent/orchestrator/skills.py` | B | `invoke_skill` split into `_invoke_skill_impl` wrapped by `track_skill`; wires `_background_callback` → `task_tracking.request_background()` and streaming status callbacks → `SkillTracker.progress()`. | No |
| `agents/client-agent/tool_discovery.py` | B | A2A stream consumer; detects `metadata.background` on status events and fires the `_background_callback` (`BackgroundCallback`). | No |
| `agents/client-agent/orchestrator/debug_commands.py` | B | `/tasks` (tree list) and `/tasks <id>` (inspect) slash commands. | No |
| `agents/debug-agents/thread-pattern-agent/agent.py` | agent | `run_background_task` skill: calls `declare_long_running` then runs the blocking worker. Reference exercise for the agent-driven path. | No |
| `shared/a2a_protocol.py` | — | `TaskStatus` enum aligned to the SDK's 9-state set. | No (mounted) |
| `prometheus_api/.../agent/base.py` | — | **`PrometheusAgent.declare_long_running()`** — emits the early `metadata.background` status. | **Yes** |
| `prometheus_api/.../agent/task_store.py` | A (per-agent store) | `RedisTaskStore` implementing the A2A `TaskStore` (`save`/`get`/`delete`), wired into `base.py` `DefaultRequestHandler`. | **Yes** |
| `frontend/utils/a2a_client.py` | frontend | `response_from_payload()`; `ConversationResponse.status` union gains `backgrounded`. | No |
| `frontend/components/message_handler.py` | frontend | `_handle_backgrounded()` ack + register id; one bounded live `cl.Step` per background task; `run_task_notifier()` per-session subscriber; idempotent `_maybe_announce_completion()`. | No |
| `frontend/main.py` | frontend | Starts `run_task_notifier` in `@cl.on_chat_start` (handle in `cl.user_session`); cancels it in `@cl.on_chat_end`. | No |
| `frontend/utils/task_events.py` | frontend | `redis.asyncio` pub/sub helpers: `subscribe()` (event generator), `node_snapshot()`/`node_state()` (race guard and latest status), `fetch_result`, key/channel builders. | No |

Tests: `agents/client-agent/tests/test_task_graph.py`, `test_task_tracking.py`, `test_tasks_command.py`,
`test_background_tasks.py`; `prometheus_api/tests/test_task_store.py`; `frontend/tests/test_background_tasks.py`.

---

## Redis schema (as-built)

All keys are conversation-scoped. Constants live in `task_graph.py`.

```
tasks:graph:{conversation_id}            SET   of task_ids in the conversation
tasks:node:{conversation_id}:{task_id}   JSON  TaskNode snapshot
tasks:roots:{conversation_id}            LIST  root task_ids (one per backgrounded/dispatching turn)
tasks:events:{conversation_id}           PUB/SUB channel — node create/transition events
tasks:result:{conversation_id}:{task_id} JSON  persisted final ConversationResponse payload (backgrounded turns)
```

**Event payload** published on `tasks:events:{conversation_id}` (consumed by the frontend watcher):

```jsonc
{ "type": "node-created" | "node-updated" | "node-completed" | "node-failed",
  "task_id": "t_…", "parent_task_id": "t_…" | null, "root_task_id": "t_…",
  "state": "working", "title": "…", "message": "…", "progress": 0.28, "ts": "…" }
```

The frontend watcher keys off `task_id` (match) and `state` (terminal check). Terminal states:
`completed | failed | canceled | rejected` (`TERMINAL_STATES`); `failed | canceled | rejected` are
`FAILURE_STATES`. Percolation depth is capped at `_MAX_PERCOLATE_DEPTH = 64` with visited-tracking against
cycles.

> **Frontend/backend contract.** `frontend/utils/task_events.py` independently re-derives these key names
> and channel; they **must stay in sync** with `task_graph.py`. Both sides are covered by tests, but if you
> rename a key, change both. The event's `{task_id, state}` shape is the other half of the contract.

---

## Data flow

### Synchronous turn (deadline disabled or beaten) — the common case

```
frontend → A2A message/stream → service._execute()
  begin_turn(conversation_id, query)
  deadline = background_deadline_seconds()      # 0 by default
  response = await chat()                        # orchestration; track_skill creates child nodes
  finish_turn(response.status)                   # root → completed/failed (if a root was materialized)
  return payload                                 # status ∈ {answer, completed, needs_info, plan_ready, …}
```

The root node is **lazy**: `begin_turn` only registers the turn; the root node is materialized on the first
skill dispatch (`_ensure_root`). Pure conversational answers never touch the graph.

### Backgrounded turn (deadline fired)

```
service._execute()
  chat_task = create_task(chat())
  await asyncio.wait({chat_task}, timeout=deadline)   # deadline elapses, chat still running
  root_id = ensure_background_root()                   # materialize + flag is_background=True
  _spawn_background_finisher(chat_task, …)             # strong-ref in service._BACKGROUND_TASKS
  store_status_update("running in the background", final=True)
  return ConversationResponse(status="backgrounded", message_metadata={"task_id": root_id})

# … meanwhile, in the detached background task …
run_background_finish(chat_task, …):
  response = await chat_task                            # finishes whenever the work is done
  payload  = build_payload(response)                    # full ConversationResponse incl. new_artifacts
  task_graph.store_result(conversation_id, root_id, payload)   # → tasks:result:…
  finish_turn_for(conversation_id, root_id, response.status)   # root → terminal → reconcile publishes node-completed
```

`_BACKGROUND_TASKS` is a module-level `set` holding a strong reference to each detached task (and a
`add_done_callback(discard)` to drop it) so the event loop doesn't GC an in-flight background task.

### Backgrounded turn (agent-declared, `declare_long_running`)

Same detach machinery, different trigger — and it fires **immediately**, not after a deadline:

```
specialist agent (e.g. thread-pattern-agent.run_background_task):
  await self.declare_long_running(context, event_queue, estimate_seconds=…)
    → emits a non-final working status with metadata={"background": true, "estimate_seconds": …}

client-agent stream consumer (tool_discovery._apply_a2a_stream_event):
  sees metadata.background on the status event → await background_callback(metadata)

skills.invoke_once._background_callback:
  task_tracking.request_background()        # sets the turn's asyncio.Event, flags skill + root is_background

service._execute:
  the bg_evt waiter wins the asyncio.wait race (before the deadline, if any) → detach now
  → identical backgrounded response + finisher as the deadline path
```

The turn-scoped `asyncio.Event` lives on the `_Turn` object created in `begin_turn`. Because `chat()` runs
as a task whose context is *copied* from `_execute` (which holds the same `_Turn` instance by reference), a
deep `request_background()` call inside the dispatched skill sets the very event `_execute` is waiting on.
This is the whole reason the signal can cross from inside `chat()` back out to the turn-level race.

### Frontend delivery (out-of-band) — one subscriber per chat session

Delivery uses a **single long-lived subscriber per chat session**, not a watcher per task. The subscriber is
started in `@cl.on_chat_start` (where the session is guaranteed live), its handle is retained in
`cl.user_session` (a strong ref — an un-referenced `asyncio.create_task` can be GC'd mid-flight), and it is
cancelled in `@cl.on_chat_end`.

```
@cl.on_chat_start:
  notifier = asyncio.create_task(run_task_notifier(cl.context.session, conversation_id))
  cl.user_session.set("task_notifier", notifier)        # strong ref → not GC'd

_handle_backgrounded(response, conversation_id):         # on a "backgrounded" turn
  cl.Message("running in the background … use /tasks").send()
  ids = cl.user_session["backgrounded_task_ids"]; ids.add(response.message_metadata["task_id"])
  node = task_events.node_snapshot(...)                  # latest status + fast-finish guard
  if node.state is terminal: _maybe_announce_completion(...)
  else: _ensure_background_progress(task_id, node.message)

run_task_notifier(session, conversation_id):             # the per-session subscriber
  init_ws_context(session)                               # bind Chainlit ctx for out-of-band sends
  async for event in task_events.subscribe(redis_url, conversation_id):   # pub/sub, whole session
    if event.task_id == event.root_task_id and event.task_id in awaited_ids:
      if is_terminal(event.state):
        _maybe_announce_completion(conversation_id, event.task_id, event.state)
      else:
        _update_background_progress(event.task_id, event.message)

_maybe_announce_completion(conversation_id, task_id, state):   # idempotent via the awaited-ids set
  if task_id not in awaited_ids: return                  # already announced / not ours
  awaited_ids.discard(task_id)
  if state == "completed":
    result = await task_events.fetch_result(redis_url, conversation_id, task_id)   # tasks:result:…
    cl.Message("✅ complete — here's the result:").send(); _handle_final_response(response_from_payload(result))
  else:
    cl.Message(f"⚠️ ended ({state}).").send()
```

Why one subscriber instead of one watcher per task:

- **No GC footgun** — the handle lives in `cl.user_session`; a fire-and-forget per-task `create_task` had no
  strong ref and could be collected during its long `await`.
- **Guaranteed context** — `init_ws_context(session)` (Chainlit) binds the captured `WebsocketSession` so
  `cl.Message().send()` and `cl.user_session` work *after* the originating request returned. This is the
  out-of-band send mechanism the design flagged as the #1 risk; it's now resolved.
- **Filtering** — the events channel carries *every* node transition (including internal sub-nodes). The
  subscriber renders only awaited root ids. Child messages already percolate to their root, so rendering
  both would duplicate each update. The awaited-id set also makes terminal announcement **idempotent**.
- **Bounded progress** — each task owns one mutable `cl.Step`; consecutive duplicate messages are ignored
  and its visible history is capped at 50 entries.

`response_from_payload()` is shared by the streaming parser (`_dict_to_response`) and the notifier, so a
backgrounded result renders **identically** to a synchronous one (artifacts, report, etc.).

**Subscribe-race guard.** The subscriber is up from chat start, so it's listening before any detach. The one
residual race — a task that updates or finishes between the `backgrounded` response and registration — is
covered by `_handle_backgrounded` reading `node_snapshot`: it seeds the Step from the latest message or
announces immediately if the node is already terminal.

`message_metadata` survives the wire: the backend sets it on the `ConversationResponse`, which is serialized
via `model_dump(exclude_none=True)` into the A2A status text part, then parsed back by
`response_from_payload`, which reads `data.get("message_metadata")`.

---

## What is implemented

- **Phase 0 — Foundations (code complete):**
  - `task_graph.py` — `TaskNode`, Redis CRUD, idempotent `reconcile()` percolation, pub/sub. Tested.
  - `shared/a2a_protocol.py` — `TaskStatus` aligned to the SDK's 9-state set. Tested.
  - `prometheus_api` `RedisTaskStore` (Layer A) wired into `DefaultRequestHandler`, with
    `PROMETHEUS_TASK_STORE=memory` escape hatch and graceful degradation when Redis is down. Tested.
    **Not yet in agent containers** — needs a base-image rebuild+push and a `PROMETHEUS_API_BASE_IMAGE_HASH`
    bump (prometheus_api is baked into the base image, never mounted).

- **Phase 1 — Single background task, turn-level (code complete, gated off):**
  - **Turn/skill tracking** — `task_tracking.py` lazy root + `track_skill`, wired into `skills.invoke_skill`
    and `service._execute`. Tested.
  - **`/tasks` + `/tasks <id>`** — `debug_commands.py`, works end-to-end (frontend forwards non-`/history`
    slash commands). Tested.
  - **Turn-level detach** — `service._execute` deadline race + `_spawn_background_finisher` +
    `run_background_finish`. Tested.
  - **Agent-driven detach (`declare_long_running`)** — `PrometheusAgent.declare_long_running` (base image)
    emits the `metadata.background` status; `tool_discovery` detects it and fires `_background_callback`;
    `skills` → `task_tracking.request_background()` sets the turn event; `service._execute` races on it and
    detaches immediately. Wired into the thread-pattern agent's `run_background_task`. Tested
    (`prometheus_api` declare tests, `tool_discovery` callback tests, `task_tracking` event tests, and a
    `service._execute` detach-on-signal integration test). **Base-image change** — reaches agent containers
    only after a base-image rebuild+push and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump.
  - **Frontend `backgrounded` handling + proactive completion notification** — `a2a_client`
    `response_from_payload`/status union; `_handle_backgrounded` ack + id registration; **one per-session
    subscriber** (`run_task_notifier`, started in `@cl.on_chat_start`, cancelled in `@cl.on_chat_end`) that
    posts the result out-of-band on completion via `init_ws_context(session)`; `task_events.subscribe`/
    `node_snapshot` pub/sub helpers. Streaming specialist messages percolate to the root and update one
    bounded live `cl.Step`, which is marked completed or failed before the final result is rendered. Tested
    (frontend suite green). *Reaches the still-open session only — see the reload limitation below.*

---

## What is missing (to finish Phase 1)

1. **Base-image roll for Layer A.** `RedisTaskStore` is code-complete but only reaches agent containers
   after a base-image rebuild+push and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump in `docker-compose.yml`.
   *Note:* turn-level backgrounding (above) does **not** depend on this — it tracks at the orchestrator/turn
   level and never calls `tasks/get`. Layer A matters for per-agent task durability and the later
   re-attach work, not for shipping Phase 1's UX.

2. **Base-image roll for `declare_long_running`.** The helper is code-complete in `prometheus_api` and
   wired through the orchestrator + thread-pattern agent, but (like Layer A) only reaches agent containers
   after a base-image rebuild+push and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump. Until then the
   thread-pattern agent's `run_background_task` runs but its `declare_long_running` call is a no-op method on
   the *old* base image, so no detach happens. Roll the image, then exercise it.

3. **Cross-reload / cross-device persistence.** Notifications reach only the **still-open** session that
   launched the task (see the reload limitation below). True persistence needs stable, user-scoped task
   ownership — designed in *"Persisting notifications across reloads"* below; gated on real auth + accounts.

4. **End-to-end test with a deliberately slow agent.** No integration test yet exercises detach → run →
   notify against a real slow specialist. Needed before flipping the deadline on.

5. **Flip `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` on** (e.g. `45`) once the above are satisfied.

### Beyond Phase 1 (design doc Phases 2–3, not started)

- Per-sub-agent stream detach (vs. turn-level), agent-to-agent non-blocking dispatch, deep multi-level
  percolation.
- Durable/restart-survivable watcher queue (Phase 1 watchers are in-process: they survive a *user*
  disconnect but **not** a client-agent restart).
- `/cancel <id>` with true downstream cancellation.
- Native A2A push + `tasks/get`/`tasks/resubscribe`/`tasks/cancel` — **blocked on extending LiteLLM's A2A
  passthrough** (the single long-pole; see the design doc).

---

## How to finish — concrete next steps

1. **Roll the base image** (`prometheus_api`): rebuild + push, bump `PROMETHEUS_API_BASE_IMAGE_HASH` in
   `docker-compose.yml`. This ships both `RedisTaskStore` (Layer A) and `declare_long_running`.

2. **Exercise the agent-driven path end-to-end** against the thread-pattern agent (no deadline needed):
   - Invoke its `run_background_task` skill (e.g. `duration_seconds=60`).
   - Confirm: a `backgrounded` ack appears almost immediately, `/tasks` shows the root `working` and
     `is_background`, and on completion the result is posted out-of-band in the same session.
   - Verify Redis: `tasks:node:{conv}:{root}` flips to `completed`, `tasks:result:{conv}:{root}` holds the
     payload, and a `node-completed` event is published.
   - Also smoke-test the time-based path: set `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS=5` and issue any
     query that takes >5 s.

3. **Flip `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` on** per environment once satisfied (the agent-driven
   path needs no flip — it's live as soon as the base image ships).

---

## Persisting notifications across reloads (needs real auth + user accounts)

**Today's limitation.** Notifications reach **only the chat session that launched the task**, and only while
its browser tab stays open. Two reasons:

1. `@cl.on_chat_start` mints a fresh `conversation_id = uuid4()` every load, so a reload starts a *new*
   conversation with no link to the in-flight task. The Task Graph node still completes and the result is
   still persisted at `tasks:result:{old_conv}:{root}` (TTL 24 h) — but nothing in the new session knows to
   look for it.
2. The subscriber is per-session and dies with the session (cancelled in `@cl.on_chat_end`).

The backend already does the durable half correctly (node + result survive in Redis with a TTL); the gap is
purely **frontend identity** — there's no stable, user-scoped handle to re-attach to.

**What true persistence needs, once auth + accounts land.** The unlock is a **stable identity to scope
in-flight tasks to**, instead of a per-tab `conversation_id`:

1. **Stable conversation identity across reloads.** Either adopt Chainlit's resumable threads (persistence
   layer + `@cl.on_chat_resume`, which restores the previous `thread_id`), or derive/persist a
   `conversation_id` from the authenticated user + thread rather than `uuid4()` per load. Then a reload
   re-enters the *same* conversation.
2. **A per-user "open background tasks" index in Redis**, written by the backend at detach time:
   `tasks:user:{user_id}:open` → set of `(conversation_id, root_task_id)`. Keyed by the authenticated
   `cl.User.identifier`, not the conversation, so it survives reloads, new tabs, and different devices.
3. **Reconcile-on-connect in `@cl.on_chat_start` / `on_chat_resume`.** With a `user_id` in hand, the frontend:
   - reads `tasks:user:{user_id}:open`;
   - for each entry, checks `node_state` — if already terminal, immediately announce via the existing
     `_maybe_announce_completion` (fetch the still-persisted `tasks:result:…` payload), and drop it from the
     index; if still running, add it to `backgrounded_task_ids` so the (now per-user) subscriber will fire.
4. **Subscribe per user, not just per conversation.** Either keep the per-conversation subscriber but start
   one per restored conversation, or add a `tasks:events:user:{user_id}` fan-out channel the backend also
   publishes terminal events to, so a single subscriber catches completions across all the user's
   conversations.
5. **Lifecycle / cleanup.** Remove ids from the per-user index on announce; TTL the index alongside the
   result keys; decide cross-device behavior (announce in every open session, or mark "delivered" once via a
   Redis flag to avoid double-posting).

This is **frontend + a small backend index**, not a protocol change — it does *not* need the LiteLLM
passthrough work (that's for restart-survivable *server-side* watchers / re-attach, a different axis). The
dependency is genuinely just **authenticated user identity**: without it there's no durable key to scope
"this user's in-flight tasks" to. Until then, the per-session subscriber is the right scope.

> **Backend prep that's cheap to do now:** have `_spawn_background_finisher` / `run_background_finish` also
> write `tasks:user:{user_id}:open` when a `user_id` is available on the request context. It's a no-op while
> auth is absent (no `user_id`), but means the durable index exists the moment accounts land.

---

## Gotchas for the next developer

- **Two triggers, one of them off by default.** Time-based detach needs
  `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS > 0`. Agent-driven detach (`declare_long_running`) is always live
  *but only on the new base image* — on an un-rolled image the method is absent/no-op and nothing detaches.
- **The background signal rides a turn-scoped `asyncio.Event` via a copied context.** `request_background()`
  must run within the same turn whose `_Turn` was set by `begin_turn` — i.e. inside `chat()` (whose context
  is copied from `_execute`). Calling it outside a turn is a silent no-op.
- **Two key definitions, one contract.** `task_events.py` (frontend) and `task_graph.py` (client-agent)
  each define the Redis key/channel names. Keep them identical.
- **`message_metadata.task_id` is load-bearing.** No `task_id` → the frontend acks but can't watch
  (`_handle_backgrounded` returns early). The backend sets it from the materialized root id.
- **Background tasks need a strong ref — both ends.** The backend holds detached tasks in
  `service._BACKGROUND_TASKS`; the frontend holds the per-session notifier in `cl.user_session`. A bare
  `asyncio.create_task(...)` with no retained handle can be GC'd mid-`await` (this was the original
  "notifications never fire" bug).
- **Out-of-band sends need `init_ws_context(session)`.** A coroutine that posts to the UI after its
  originating request returned must bind the captured `WebsocketSession` first; `run_task_notifier` does this
  once at startup. Don't rely on contextvar copying alone.
- **Notifications are session-scoped today.** The subscriber dies with the chat session and the
  `conversation_id` is per-tab, so a reload loses the link to in-flight tasks. Cross-reload persistence needs
  authenticated user identity — see *"Persisting notifications across reloads."*
- **Testable logic stays out of `prometheus_api`.** `run_background_finish` lives in `task_tracking` (not
  `service`) specifically so it can be unit-tested without importing the heavy orchestrator/prometheus_api
  stack and fighting `sys.modules` stubs. Keep new detach logic there.
- **In-process watchers don't survive a client-agent restart.** That's a Phase 2b gap, by design.
