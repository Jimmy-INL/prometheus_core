# Background / Long-Running Tasks

Status: **design + Phase 0/1 in progress** (turn-level backgrounding implemented, gated off by default)
Owner: platform
Related: [`background-tasks-implementation.md`](./background-tasks-implementation.md) (as-built reference),
[`architecture.md`](../docs/dev-docs/architecture.md), [`prometheus_api_a2a_routing_refactor_plan.md`](./prometheus_api_a2a_routing_refactor_plan.md)

> **As-built reference.** This document is the design + rationale + phasing. For the *as-built*
> implementation (file map, Redis schema, data flow, the `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` switch,
> and the concrete "what's left to finish Phase 1" checklist), see
> [`background-tasks-implementation.md`](./background-tasks-implementation.md).

## Why

Today the whole stack assumes **task lifetime == HTTP request lifetime**. Every A2A
call (`message/send` with `blocking: true`, or `message/stream`) is awaited to a
terminal event, up to a 900 s timeout:

- frontend `A2AClient.send()` blocks on a streaming response until a terminal event
  (`frontend/utils/a2a_client.py`),
- client-agent `call_a2a_agent()` blocks on each downstream call
  (`agents/client-agent/tool_discovery.py:430`, `blocking: True` at line 478,
  `timeout_seconds = 900.0` at line 518),
- the workflow executor blocks on each batch via `asyncio.gather`
  (`agents/client-agent/workflow_library/executor.py`).

There is no notion of work that outlives the request that started it. This document
designs that capability and tracks the Phase 0/1 implementation.

The long-term goal is a **hierarchical** multi-agent system: an agent may dispatch
work to another agent, that work may turn out to be long-running, and the fact that
the first agent is *waiting* (and won't answer immediately) must percolate back to the
user.

## Core reframe

> **Decouple task execution from the request that starts it.** A task is a durable,
> addressable, hierarchical unit of work. The user's HTTP connection is just one
> (optional) viewer of it.

Three pillars:

1. **Durable Tasks** — task state lives in Redis, not in-process memory; it outlives
   any request.
2. **The Task Graph** — the client-agent owns a per-conversation *tree* of tasks (who
   dispatched whom). This tree is the backbone for `/tasks`, notifications, inspection,
   cancellation, **and** hierarchical percolation.
3. **Detach + Watch + Notify** — the orchestrator can hand control back to the user
   while keeping a server-side *watcher* subscribed to the still-open sub-agent stream;
   completion is published to the user's session out-of-band.

---

## Data model (detailed)

All state lives in Redis (already the platform state layer: conversation state,
status updates, artifact registry). Two layers:

### Layer A — per-agent durable Task store (`prometheus_api`)

Replaces the volatile `InMemoryTaskStore` (`prometheus_api/.../agent/base.py:1646`)
with a `RedisTaskStore` implementing the A2A `TaskStore` interface (`save`/`get`/`delete`).
This persists the A2A `Task` object itself so a task can stay `working` across requests
and (eventually) be re-attached to.

```
task:{task_id}                    → JSON A2A Task snapshot {id, contextId, status{state,message,timestamp}, artifacts, history}
task:{task_id}:history            → LIST of status-update JSON (append-only, capped)
```

TTL: terminal tasks expire after `TASK_TTL` (default 24 h). Non-terminal tasks are
refreshed on every update (so an active task never expires out from under a watcher).

> **Base-image note.** `RedisTaskStore` lives in `prometheus_api`, which is baked into
> the base image and **must not be mounted** into containers (see
> `feedback_no_mount_prometheus_api`). Shipping it requires a base-image rebuild + push
> and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump. Phase 0 is therefore split so the
> client-agent and frontend pieces (which need no base-image change) can land and be
> tested independently of the base-image roll.

### Layer B — the Task Graph (client-agent)

The orchestrator owns the cross-agent *tree*. This is the new core abstraction and is
**independent of the base image** (lives in the client-agent). Keys are
conversation-scoped:

```
tasks:graph:{conversation_id}              → SET of task_ids in this conversation
tasks:node:{conversation_id}:{task_id}     → JSON TaskNode (schema below)
tasks:events:{conversation_id}             → Redis pub/sub channel (state-change events)
tasks:roots:{conversation_id}              → LIST of root task_ids (one per user turn)
```

#### `TaskNode` schema

```jsonc
{
  "task_id":        "t_ab12…",          // stable id; == A2A task id when we own it
  "conversation_id":"conv_…",
  "parent_task_id": "t_root…" | null,    // null for a root (user-turn) node
  "child_task_ids": ["t_cd34…", …],      // tasks this node dispatched

  "agent":          "thermal-agent",     // null for the root/orchestrator node
  "skill":          "run_thermal_sim",
  "title":          "Thermal simulation (assembly-7)",  // human label for /tasks

  "state":          "working",           // submitted|working|input-required|
                                         // completed|failed|canceled|rejected
  "is_background":   true,               // detached from the user's request?
  "waiting_on":     ["t_cd34…"],         // non-terminal children blocking this node

  "created_at":  "2026-06-06T18:00:00Z",
  "started_at":  "2026-06-06T18:00:01Z",
  "updated_at":  "2026-06-06T18:04:12Z",
  "finished_at":  null,

  "last_status_message": "Solving step 142/500…",
  "progress":            0.28,           // optional 0..1 if the agent reports it

  "result_ref":   "artifact:…" | null,   // pointer to final result (artifact id)
  "error":        null
}
```

#### State vocabulary

We align on the A2A SDK's `TaskState` (8 states) everywhere, replacing the 4-state
custom enum in `shared/a2a_protocol.py`:
`submitted | working | input-required | completed | failed | canceled | rejected | auth-required`.

Terminal states: `completed`, `failed`, `canceled`, `rejected`. Everything else is
*non-terminal* (a node with any non-terminal descendant is itself non-terminal).

#### Events on `tasks:events:{conversation_id}`

Every node create/transition publishes a compact event:

```jsonc
{ "type": "node-created" | "node-updated" | "node-completed" | "node-failed",
  "task_id": "t_…", "parent_task_id": "t_…" | null,
  "state": "working", "title": "…", "message": "…",
  "root_task_id": "t_root…", "result_ref": "artifact:…" | null,
  "ts": "2026-06-06T18:04:12Z" }
```

The frontend's per-session subscriber consumes these (see *Notify*).

### Why two layers

Layer A is **per-agent** and local to each agent process — it answers "what is the
state of *this* task on *this* agent?" (the A2A `tasks/get` contract). Layer B is
**cross-agent** and owned by the orchestrator — it answers "what is the whole tree of
work for this conversation, and where is it blocked?" The user-facing features
(`/tasks`, notifications, percolation) are all driven by Layer B. Layer A becomes
strictly necessary only once we want restart-survivable re-attachment (Phase 2b/3).

---

## Percolation (how "I'm waiting" reaches the user)

Percolation is the **up-propagation of non-terminal state through the Task Graph**, so
that the *root* node (the one created by the user's message) reflects the deepest thing
still running. The user's status == the root node's status.

### Invariant

> A node is in a terminal state **iff** its own work is finished *and* every child is
> terminal. Equivalently: a node stays `working` while `waiting_on` is non-empty.

### Algorithm

When a node `N` transitions (its own work finishes, or a child reports a new state),
run `reconcile(N)`:

```
reconcile(node N):
    # 1. recompute what N is still blocked on
    N.waiting_on = [c for c in N.child_task_ids if state(c) is non-terminal]

    # 2. decide N's effective state
    if N.own_work_done and N.waiting_on is empty:
        if any child failed and N.policy == fail_fast:  new = failed
        else:                                            new = completed
    elif N.waiting_on not empty:
        new = working                       # blocked on descendants
        N.last_status_message = summarize(N.waiting_on)   # e.g. "waiting on thermal-sim (4m)"
    else:
        new = N.own_state                   # still doing its own work

    # 3. persist + publish only if something changed
    if new != N.state or message changed:
        N.state = new; N.updated_at = now()
        save(N); publish(tasks:events, node-updated|completed|failed for N)

        # 4. propagate to the parent
        if N.parent_task_id and new is terminal-or-message-changed:
            reconcile(parent(N))
```

Propagation is **synchronous and idempotent**: a child completing calls
`reconcile(parent)`, which may itself complete and call `reconcile(grandparent)`, up to
the root. Because step 3 only publishes on real change, a no-op transition stops the
cascade (prevents event storms / infinite loops in cyclic-by-bug graphs — we also cap
depth and detect already-visited nodes within one cascade).

### Worked example

```
t_root (orchestrator, user turn)                 working  ← user sees this
└─ t_synth  (synthesis-agent)                    working
   ├─ t_corr  (corrosion-agent)      completed ✓
   └─ t_therm (thermal-agent, long sim)          working   waiting_on=[]   "step 142/500"
```

- User sees root: **"working — waiting on thermal-agent (Thermal simulation, 4m, step 142/500)"**.
  `t_root.waiting_on = [t_synth]`, `t_synth.waiting_on = [t_therm]`; the root's
  `last_status_message` is derived from the deepest blocking leaf.
- `t_corr` completing fires `reconcile(t_synth)`. `t_synth` is still blocked on
  `t_therm`, so it stays `working` (no change beyond message) and the cascade stops.
- When `t_therm` completes, `reconcile(t_synth)` finds `waiting_on` empty; if
  `t_synth`'s own work is done it becomes `completed`, which fires
  `reconcile(t_root)`, which (own work done, no pending children) becomes `completed`.
  A `node-completed` event for the root is published → the frontend posts the final
  answer.

This is exactly the prompt's requirement: *"the first agent has to wait for the
long-running task and won't come back with an answer immediately"* — the root stays
`working` with a message that names the deep dependency, and the user is told what the
bottleneck is, live.

### Where percolation runs in Phase 1 vs later

- **Phase 1** uses a *shallow* tree: `root → one specialist`. Percolation degenerates
  to "root mirrors the one backgrounded child." The full `reconcile` is implemented now
  (it costs nothing extra) so deeper trees work without rework.
- **Phase 2** adds the intermediate nodes (`t_synth` above) and the agent-to-agent
  dispatch that creates depth.

---

## Detach + Watch + Notify

### Becoming a background task

- **Proactive** — a specialist declares it up front via a new base-class helper
  `self.declare_long_running(estimate=…)`, which emits an early status with
  `metadata={"background": true}`. Simulation-class agents use this.
- **Soft promotion** — the orchestrator dispatches with a soft deadline (default 45 s).
  If the sub-agent stream has not reached a terminal event by the deadline, the
  orchestrator promotes the task to background. Short tasks feel synchronous; long ones
  detach gracefully.

### Implementation note — turn-level detach (Phase 1 realization)

Phase 1 realizes the watcher at the **turn level** rather than per sub-agent stream:
far less invasive and equally correct, since `chat()` already runs in-process and already
updates the Task Graph via `task_tracking`. `service._execute` races `chat()` against a
soft deadline (`PROMETHEUS_BACKGROUND_DEADLINE_SECONDS`, default `0` = disabled). If the
deadline fires, the orchestration is **detached** — left running as a background
`asyncio.Task` (strong-ref'd in `service._BACKGROUND_TASKS`) — and the user gets a
`backgrounded` response. `task_tracking.run_background_finish` awaits the detached task,
finalizes the root node (percolation publishes the completion event), and persists the
final payload via `task_graph.store_result` for the frontend to render on notification.
Sub-agent calls are unchanged, so this needs no LiteLLM change. Per-sub-agent stream
detach (next) is the Phase 2 generalization.

### The watcher (works through LiteLLM **today**)

When the orchestrator backgrounds a task it does **not** stop the work and does **not**
need `tasks/get`:

1. The `message/stream` to the sub-agent (already open, already through LiteLLM) is
   moved into a detached background `asyncio.Task` in the client-agent — the *watcher*.
2. The orchestrator emits a terminal `backgrounded` event to the user (a `status-update`
   with `metadata={"backgrounded": true, "task_id": …}`, `final: true`) and closes the
   user-facing stream. The user regains input control.
3. The watcher keeps consuming the sub-agent SSE stream; on each event it updates the
   Task Graph node and publishes to `tasks:events:{conversation_id}`. On the terminal
   event it marks the node terminal, stores `result_ref`, and runs `reconcile` up the
   tree.

> **Limitation (honest):** an in-process watcher survives a *user* disconnect but **not
> a client-agent restart**. Phase 2b replaces it with a durable watcher queue
> (restart-survivable, rebuilt from non-terminal Task Graph nodes, re-attaching via
> `tasks/resubscribe`). That re-attach needs the LiteLLM passthrough extension (below).

### Notify (Chainlit out-of-band)

After detach the frontend has no open request, so notifications are pushed into the
Chainlit session:

- In `@cl.on_chat_start`, start a per-session subscriber coroutine on
  `tasks:events:{conversation_id}` (Redis pub/sub). Starting it inside the chat-start
  handler lets it inherit the Chainlit session context (contextvars propagate to
  `asyncio.create_task`). **This context propagation is the #1 thing to validate with a
  spike before building on it** (see Risks).
- `state-change` → update a live `cl.TaskList` (Chainlit's native RUNNING/DONE/FAILED
  panel).
- `node-completed` / `node-failed` for a root or backgrounded node → post a
  `cl.Message` and render the result via the existing `render_artifacts()` (fetched from
  the artifact registry by `result_ref`).

---

## Frontend `/tasks`, inspection, cancel

Following the existing `/history` pattern (manual `startswith("/")` in
`frontend/main.py`, reads Redis directly via a read-only client):

- **`/tasks`** — read `tasks:graph:{conversation_id}`; render the tree (short id, agent,
  state, elapsed, parent) as a `cl.TaskList` + a message table. *Reads go straight to
  Redis* (fast, mirrors `/history`).
- **`/tasks <id>`** — inspect one task: full `task:{id}:history`, current state,
  elapsed, sub-tree, artifacts produced so far.
- **`/cancel <id>`** — *mutating*, routed through the orchestrator (A2A): walk the
  sub-tree, stop watchers, mark nodes `canceled`, best-effort downstream cancel.

A new frontend response status — **`backgrounded`** — is added to the existing set
(`needs_info | plan_ready | completed | answer | error`). `A2AClient._stream_request`
recognizes the `backgrounded` terminal event; the frontend shows "running in the
background as task X" and returns control; the subscriber delivers the eventual result.

We also register `/tasks` and `/cancel` in Chainlit's native command palette (for
autocomplete) while keeping the manual parser for `/history` parity.

---

## LiteLLM readiness assessment

**Is the current LiteLLM (`v1.83.3-stable`, pinned in `docker-compose.yml`) ready for
this plan?**

**For Phase 0 and Phase 1: yes — no LiteLLM change required.** The reason is that the
detach/watch design deliberately uses *only* the two methods LiteLLM already forwards:

| A2A method | LiteLLM routing today | Needed in Phase 0/1? |
|---|---|---|
| `message/send` | ✅ `POST /a2a/{agent}/message/send` (method in URL path, `tool_discovery.py:512`) | yes (existing) |
| `message/stream` | ✅ `POST /a2a/{agent}` with method in the JSON-RPC body — LiteLLM exposes **no** `/message/stream` sub-route (`tool_discovery.py:521-527`) | yes — this is what the watcher rides |
| `tasks/get` | ❌ not forwarded | no |
| `tasks/resubscribe` | ❌ not forwarded | no |
| `tasks/cancel` | ❌ not forwarded | no (Phase 1 cancel marks the graph + stops the watcher; true downstream cancel is best-effort) |
| `tasks/pushNotificationConfig/*` | ❌ not forwarded | no |

LiteLLM's A2A gateway is **path-routed, not a transparent JSON-RPC relay**: it forwards
specific URL paths to the registered agent base URL (stored from the `url` field at
`POST /v1/agents`). The orchestrator keeping a server-side `message/stream` open is a
plain long-lived HTTP/SSE call through a path LiteLLM already proxies — so a backgrounded
task is fully supported on the current version.

**For Phase 2b/3: not ready — requires work.** Restart-survivable re-attachment
(`tasks/resubscribe`), pull-based status (`tasks/get`), true downstream cancellation
(`tasks/cancel`), and native A2A push notifications (`tasks/pushNotificationConfig/*`)
all require those JSON-RPC methods to reach specialist agents. Because all agent traffic
must go through LiteLLM (`project_litellm_routing`), enabling them means **extending
LiteLLM's A2A passthrough** to forward `/a2a/{agent}/tasks/*` (and the push-config
paths) to the agent's base URL — either an upstream contribution or a thin proxy/shim in
front of (or configured into) LiteLLM. This is the single long-pole dependency for the
durable/hierarchical phases and should be scoped before Phase 2b starts.

**Net:** the plan is sequenced so that everything user-visible (durable task state, the
Task Graph, backgrounding, `/tasks`, notifications, inspection) ships on the **current
LiteLLM**, and the LiteLLM passthrough work is isolated to the later durability/scale
phases.

---

## Phasing

| Phase | Deliverable | LiteLLM change? |
|------|-------------|------|
| **0 — Foundations** | `RedisTaskStore` (base image); align `TaskState`; Task Graph registry + `reconcile` + pub/sub in client-agent. | No |
| **1 — Single background task, end-to-end** | Soft-promotion + `declare_long_running`; orchestrator stream-watcher + `backgrounded` response; frontend subscriber + `cl.TaskList`; `/tasks`, `/tasks <id>`; completion notification. | No |
| **2a — Centralized continuation** | Long-running *workflow steps*: persist plan, detach, resume-on-completion; `/cancel`. | No |
| **2b — Distributed continuation + durability** | Agent-to-agent non-blocking dispatch; continuation via `ContextStateStore`; durable watcher queue (restart-survivable); full multi-level percolation. | Partly (`tasks/resubscribe`) |
| **3 — Polish** | Native A2A push notifications + `tasks/get`/`tasks/resubscribe`/`tasks/cancel` through LiteLLM; cancellation propagation; retries; TTL/GC. | **Yes (extend passthrough)** |

### Phase 0 work items

1. ✅ `agents/client-agent/task_graph.py` — `TaskNode` model, Redis CRUD, `reconcile`,
   pub/sub publish. **(no base image)** — *done.*
2. ✅ `tests/test_task_graph.py` — percolation tests (completion cascade, blocked-parent,
   fail_fast, deepest-blocking message, tree build). **6 passing.**
3. ✅ `shared/a2a_protocol.py` — `TaskStatus` enum aligned to the SDK's full state set;
   `tests/infrastructure/test_a2a_protocol.py` updated. **16 passing.**
4. ✅ `prometheus_api`: `RedisTaskStore` (`prometheus_api/agent/task_store.py`) + wired
   into `DefaultRequestHandler` (`base.py:1644`), exported from `agent/__init__.py`;
   `tests/test_task_store.py` **6 passing**, ruff + mypy clean. Default store is now
   Redis (degrades to in-process dict if Redis is down; `PROMETHEUS_TASK_STORE=memory`
   forces the SDK's volatile store). **Code complete — but lands in the agent containers
   only after a base-image rebuild + push and a `PROMETHEUS_API_BASE_IMAGE_HASH` bump
   (prometheus_api is baked into the base image, never mounted).**

`reconcile` distinguishes a node's `own_state` (what its own work reports) from its
effective `state` (after considering children). The percolation cascade is idempotent —
it persists/publishes/propagates only on real change, which both terminates the cascade
and prevents event storms. Depth is capped at 64 and visited-tracked against cycles.

### Phase 1 work items

5a. ✅ `orchestrator/task_tracking.py` — turn/skill → Task Graph integration. Lazy root
   (created only when a turn dispatches a skill); `track_skill` async context manager wraps
   each dispatch, creating a child node and finalizing it from the result. Parent linkage
   via context vars so future nested dispatch links to its caller. Wired into
   `skills.invoke_skill` (body split into `_invoke_skill_impl`) and `service._execute`
   (`begin_turn`/`finish_turn` around `chat()`). `tests/test_task_tracking.py` **6 passing.**
5b. ✅ `/tasks` command (`orchestrator/debug_commands.py`) — list (tree view) + `/tasks <id>`
   inspect (with short-id prefix match). Handled server-side alongside `/agents`/`/artifacts`;
   returns an `answer` with a plain-text tree **and** the structured tree in
   `message_metadata["tasks"]` for richer frontend rendering. Works end-to-end today because
   the frontend already forwards non-`/history` slash commands. `tests/test_tasks_command.py`
   **6 passing.**
6. ✅ orchestrator: soft-deadline + promote-to-background (turn-level detach). `service._execute`
   races `chat()` against `PROMETHEUS_BACKGROUND_DEADLINE_SECONDS` (default `0` = disabled);
   on timeout it detaches the orchestration into a background task, returns a `backgrounded`
   response, and `task_tracking.run_background_finish` finalizes the root + persists the result
   (`task_graph.store_result`). All testable logic lives in `task_tracking` (no prometheus_api
   dep). `tests/test_background_tasks.py` **9 passing**; full client-agent suite 62 green, ruff
   clean. *(Gated off by default, so safe to ship ahead of the frontend pieces.)*
7. ⬜ base class: `declare_long_running()` helper for proactive (pre-deadline) detach. **(base image)**
8. ✅ `frontend/utils/a2a_client.py`: handle the `backgrounded` response →
   `ConversationResponse(status="backgrounded", …)`. Added `response_from_payload()` (shared by the
   streaming parser and the background notifier). Tested.
9. 🟡 frontend per-session out-of-band delivery — **partially done.** `frontend/utils/task_events.py`
   (`redis.asyncio` pub/sub: `wait_for_task`/`fetch_result`) + `message_handler._handle_backgrounded` /
   `_watch_background_task` ack the detach and post the completion result via `_handle_final_response`.
   `tests/test_background_tasks.py` **8 passing**; full frontend suite 80 green. **Still missing:** the live
   `cl.TaskList` progress panel (interim `node-updated` events). *(Needs the Chainlit out-of-band context
   spike — see Risks; the completion-message path is already proven via `asyncio.create_task` inheriting the
   session context.)*
10. ⬜ End-to-end test with a deliberately slow debug agent.

---

## Risks / open questions

1. **LiteLLM passthrough is the long-pole** for Phase 2b/3 (see assessment). Decide
   early: extend LiteLLM vs. stay on the stream-watcher model.
2. **Chainlit out-of-band messaging** — pushing a `cl.Message` from a background
   subscriber relies on session-context propagation. Needs a focused spike before
   Phase 1 UX is built on it.
3. **Watcher durability** — in-process watchers die on client-agent restart (Phase 1
   gap, fixed in 2b). Phase 1 is explicit that a backgrounded task survives a *user*
   disconnect, not a *client-agent* restart.
4. **Result assembly** — a backgrounded multi-step plan needs a defined "assemble final
   answer on completion" step in the orchestrator; single-task Phase 1 just renders the
   one `result_ref`.
