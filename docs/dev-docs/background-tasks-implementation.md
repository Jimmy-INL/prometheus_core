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
Redis pub/sub channel and renders the result out-of-band when the task completes.

The whole feature is **gated off** by `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS=0` (the default), so it ships
dark and the synchronous request/response path is byte-for-byte unchanged until someone flips it on.

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
done, _ = await asyncio.wait({chat_task}, timeout=deadline)
if chat_task in done:
    response = chat_task.result()                      # beat the deadline → return normally
    ...
else:
    root_id = task_tracking.ensure_background_root()   # missed it → detach
    self._spawn_background_finisher(chat_task, ...)
    return ConversationResponse(status="backgrounded", message_metadata={"task_id": root_id}, ...)
```

> **Why default off:** the frontend and base-image pieces are sequenced to land independently. Until the
> frontend understands `backgrounded` (now done) *and* you've validated the end-to-end flow against a real
> slow agent, leaving the deadline at `0` keeps production on the proven synchronous path. Flip it on (per
> environment, e.g. `45`) only after the end-to-end smoke test.

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
| `agents/client-agent/orchestrator/task_tracking.py` | B | Turn/skill → graph integration: `begin_turn`/`finish_turn`, lazy root, `track_skill` ctx manager, `background_deadline_seconds`, `ensure_background_root`, `run_background_finish`. | No |
| `agents/client-agent/orchestrator/service.py` | B | `_execute()` deadline race + detach; `_spawn_background_finisher`; builds the `backgrounded` response. | No |
| `agents/client-agent/orchestrator/skills.py` | B | `invoke_skill` split into `_invoke_skill_impl` wrapped by `track_skill`. | No |
| `agents/client-agent/orchestrator/debug_commands.py` | B | `/tasks` (tree list) and `/tasks <id>` (inspect) slash commands. | No |
| `shared/a2a_protocol.py` | — | `TaskStatus` enum aligned to the SDK's 9-state set. | No (mounted) |
| `prometheus_api/.../agent/task_store.py` | A (per-agent store) | `RedisTaskStore` implementing the A2A `TaskStore` (`save`/`get`/`delete`), wired into `base.py` `DefaultRequestHandler`. | **Yes** |
| `frontend/utils/a2a_client.py` | frontend | `response_from_payload()`; `ConversationResponse.status` union gains `backgrounded`. | No |
| `frontend/components/message_handler.py` | frontend | `_handle_backgrounded()` ack + spawn; `_watch_background_task()` watcher. | No |
| `frontend/utils/task_events.py` | frontend | `redis.asyncio` pub/sub helpers: `wait_for_task`, `fetch_result`, key/channel builders. | No |

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
  "state": "working", "title": "…", "message": "…", "ts": "…" }
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

### Frontend delivery (out-of-band)

```
message_handler._handle_response(response):
  status == "backgrounded" → _handle_backgrounded(response, conversation_id):
    cl.Message("running in the background … use /tasks").send()
    task_id = response.message_metadata["task_id"]
    asyncio.create_task(_watch_background_task(conversation_id, task_id))   # inherits Chainlit session ctx

_watch_background_task(conversation_id, task_id):
  state  = await task_events.wait_for_task(redis_url, conversation_id, task_id)  # pub/sub, blocks
  if state is None:        return                      # Redis unavailable → silent no-op
  if state != "completed": cl.Message("⚠️ ended ({state})").send(); return
  result = await task_events.fetch_result(redis_url, conversation_id, task_id)   # tasks:result:…
  cl.Message("✅ complete — here's the result:").send()
  _handle_final_response(response_from_payload(result))   # same renderer as a synchronous final answer
```

`response_from_payload()` is shared by the streaming parser (`_dict_to_response`) and the background
notifier, so a backgrounded result renders **identically** to a synchronous one (artifacts, report, etc.).

**Subscribe-race guard.** `wait_for_task` subscribes to the channel first, *then* reads the current node
state once — so a task that completes between detach and subscribe is still detected (the node is already
terminal) rather than hanging forever waiting for an event that already fired.

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
  - **Frontend `backgrounded` handling** — `a2a_client` `response_from_payload`/status union;
    `message_handler` ack + watcher; `task_events` pub/sub helpers. Tested (frontend suite green).

---

## What is missing (to finish Phase 1)

1. **Base-image roll for Layer A.** `RedisTaskStore` is code-complete but only reaches agent containers
   after a base-image rebuild+push and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump in `docker-compose.yml`.
   *Note:* turn-level backgrounding (above) does **not** depend on this — it tracks at the orchestrator/turn
   level and never calls `tasks/get`. Layer A matters for per-agent task durability and the later
   re-attach work, not for shipping Phase 1's UX.

2. **`declare_long_running()` base-class helper (proactive detach).** A specialist that *knows* it will be
   slow should be able to detach up front rather than waiting out the soft deadline. The design calls for
   `self.declare_long_running(estimate=…)` emitting an early status with `metadata={"background": true}`.
   Lives in `prometheus_api` → **base-image change.** Today only *soft promotion* (deadline) exists.

3. **Live `cl.TaskList` progress panel.** The frontend currently posts a one-shot "running in the
   background" ack and a completion message. It does **not** yet render Chainlit's native RUNNING/DONE
   panel or stream interim `node-updated` progress. The watcher already receives every event on
   `tasks:events:…` — wiring those into a `cl.TaskList` is the remaining UX piece.
   *Caveat:* this needs the **Chainlit out-of-band context spike** (does session context propagate into a
   `create_task` subscriber well enough to mutate a `cl.TaskList`?). The completion-message path is already
   proven to work via `asyncio.create_task` inheriting the session context.

4. **End-to-end test with a deliberately slow agent.** No integration test yet exercises detach → run →
   notify against a real slow specialist. Needed before flipping the deadline on.

5. **Flip `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` on** (e.g. `45`) once 3–4 are satisfied.

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

1. **Smoke-test the happy path now (no base-image roll needed):**
   - Set `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS=5` in the client-agent env.
   - Issue a query that takes >5 s. Confirm: a `backgrounded` ack appears, `/tasks` shows the root as
     `working`, and on completion the result is posted out-of-band in the same session.
   - Verify Redis: `tasks:node:{conv}:{root}` flips to `completed`, `tasks:result:{conv}:{root}` holds the
     payload, and a `node-completed` event is published.

2. **Build the `cl.TaskList` panel** (`frontend`, no base image):
   - Do the context-propagation spike first (mutate a `cl.TaskList` from the existing watcher coroutine).
   - On `node-created`/`node-updated`/`node-completed`/`node-failed`, upsert a `cl.Task` keyed by `task_id`,
     mapping graph state → `cl.TaskStatus`. The watcher already has the event stream.

3. **Ship Layer A** (`prometheus_api`, base image): rebuild + push the base image, bump
   `PROMETHEUS_API_BASE_IMAGE_HASH`. Then add `declare_long_running()` to `PrometheusAgent` and re-roll.

4. **Add the slow-agent integration test**, then **flip the deadline on** per environment.

---

## Gotchas for the next developer

- **The default is off.** If you can't reproduce backgrounding, check
  `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` — `0`/unset means the detach branch is never taken.
- **Two key definitions, one contract.** `task_events.py` (frontend) and `task_graph.py` (client-agent)
  each define the Redis key/channel names. Keep them identical.
- **`message_metadata.task_id` is load-bearing.** No `task_id` → the frontend acks but can't watch
  (`_handle_backgrounded` returns early). The backend sets it from the materialized root id.
- **Background tasks need a strong ref.** Detached tasks are held in `service._BACKGROUND_TASKS`; dropping
  that would let the loop GC them mid-flight.
- **Testable logic stays out of `prometheus_api`.** `run_background_finish` lives in `task_tracking` (not
  `service`) specifically so it can be unit-tested without importing the heavy orchestrator/prometheus_api
  stack and fighting `sys.modules` stubs. Keep new detach logic there.
- **In-process watchers don't survive a client-agent restart.** That's a Phase 2b gap, by design.
