# Hierarchical Multi-Agent Delegation — Design Note

Status: **design** (bridges two existing plans; resolves the seam between them)
Owner: platform
Related: [`background-tasks.md`](./background-tasks.md) (Task Graph, percolation, detach/notify),
[`background-tasks-implementation.md`](./background-tasks-implementation.md) (as-built),
[`prometheus_api_a2a_routing_refactor_plan.md`](./prometheus_api_a2a_routing_refactor_plan.md) (shared router)

## Why this note exists

We have two design docs that each solve half of "deep multi-agent hierarchies," and they don't quite meet:

- **`background-tasks.md`** gives us the **Task Graph** (a conversation-scoped tree of task nodes), **percolation**
  (a node stays non-terminal while any descendant runs, so the root = the user's status), and **detach + watch +
  notify**. Its `reconcile()` is already depth-agnostic. But its Task Graph writer (`task_tracking`) lives only in
  the **client-agent**, so only the client-agent can create nodes.
- **`prometheus_api_a2a_routing_refactor_plan.md`** moves A2A **transport, discovery, delegation context, and loop
  detection** into a shared router in `prometheus_api`, so **specialists can delegate to peers**. But it doesn't say
  anything about the Task Graph.

The seam: once a specialist delegates to a peer *without the client-agent in the loop*, **who creates the Task Graph
node for that hop?** The client-agent never sees it. This note resolves that, and uses it to answer the broader set
of hierarchy questions.

---

## The core decision: split the orchestrator

"Move the orchestrator into the base class?" — **partly.** Split it along a transport/planning line:

| Concern | Today | Target | Rationale |
|---|---|---|---|
| A2A transport, discovery, capability cache, streaming, error taxonomy | client-agent (`tool_discovery.py`) | **base class** (`prometheus_api` router) | Every delegating agent needs it. |
| Delegation context, hop/loop limits, allowlist, downstream auth | client-agent (implicit) | **base class** (router policy) | Must be enforced uniformly, not per-agent. |
| **Task Graph writes** (node create + percolation on delegate) | client-agent (`task_tracking.py`) | **base class** (with the router) | The delegation site must be the writer (see below). |
| Task Graph **read / presentation** (`/tasks`, root = user status, completion notify) | client-agent | **client-agent** | It's the user-facing surface. |
| LLM planning: `understand_query → route → plan → approve → execute`, decomposition, workflow library, user follow-up | client-agent | **client-agent** | Domain logic of being the *user-facing* orchestrator. A specialist delegating to one known peer needs no planner. |

So the unit that moves is the **router + Task Graph writer**, not "the orchestrator." The **planner stays.** A
specialist gets delegation by calling a high-level SDK method; it does not gain a LangGraph.

> **The missing link, stated plainly:** `task_tracking` (currently client-agent-only) **moves into the base-class
> router**, because the agent that *issues* a delegation is the only one positioned to create that hop's node with
> correct parentage. This is the one decision neither existing doc makes, and everything below depends on it.

---

## Q: Who owns the task list?

Separate **substrate ownership** from **presentation ownership**, and keep the two existing layers:

- **Layer A — per-agent A2A `Task`** (`RedisTaskStore`, shipped): each agent owns *its own* task lifecycle
  (`tasks/get` contract). Local to that agent.
- **Layer B — the cross-agent Task Graph** (`tasks:node:{conv}:{id}` etc.): **conversation-scoped shared state in
  Redis, owned by no single agent.**

Ownership split:

- **Writes are owned by the base-class router.** Whenever *any* agent delegates, its router creates the child node
  with `parent_task_id` taken from the delegation context. This is what keeps the graph correct in a distributed
  chain the client-agent never observes.
- **Read/presentation is owned by the client-agent.** The root node is the user's status; `/tasks` is its view; the
  detach watcher + completion notification are its job.

Net: **shared substrate, router writes, client-agent presents.**

---

## Q: How do agents dispatch to sub-agents?

The routing-refactor SDK surface, in the base class:

```python
result = await self.agent_router.invoke_skill(
    agent_id="artifact-debug-agent", skill_id="create_svg_artifact",
    params={...}, conversation_id=conversation_id,
)
```

Under the hood: build `message/send` or `message/stream` → **through LiteLLM** (`/a2a/{agent}`, never direct URLs)
→ attach the delegation context (below) → **create the Task Graph child node** → consume the stream (status/artifact
events update the node; percolation runs). Gated `AGENT_ROUTING_ENABLED=false` until proven.

Loop safety: hard `hop_count` cap + `visited_agents` rejection. Start simple (hop count + repeated-agent), not
graph-theoretic. Downstream auth is **proxy-owned** (LiteLLM authenticates to the specialist), not
inbound-token-forwarded — needs a LiteLLM-side token decision.

---

## Q: How do deep hierarchies actually form?

Two structurally different sources of depth (both already phased in `background-tasks.md`):

1. **Plan depth (centralized, exists today):** the client-agent dispatches a multi-step plan; step *N*'s output
   feeds step *N+1*. The tree is the client-agent's plan. `track_skill`'s `_nested_parent` contextvar already nests
   these within the client-agent process.
2. **Delegation depth (distributed, the new capability):** a specialist itself calls a peer
   (`data-agent → artifact-debug-agent`). This is routing-refactor **Phase 4** and is what makes the hierarchy truly
   deep.

`reconcile()` is already depth-agnostic (capped at 64, visited-tracked). The infrastructure for deep trees exists;
what's missing is (a) specialists being *able* to delegate and (b) node-writing at the delegation site.

---

## Concrete: `task_tracking` as a writer-from-anywhere

Moving `task_tracking` into the base-class router changes one thing fundamentally: **parent linkage stops being a
process-local contextvar and becomes wire-carried delegation context** (contextvars don't cross the network).

Within a single agent process, a contextvar still tracks "my current node." Across the wire, parentage rides in the
delegation context. The handshake:

```
INBOUND (base executor, on every _execute):
  ctx = DelegationContext.from_message_metadata(message)   # caller_node_id, hop_count, visited, …
  my_node = task_graph.register_self(
      task_id=context.task_id,                # my A2A task id == my node id
      conversation_id=ctx.conversation_id,
      parent_task_id=ctx.caller_node_id,      # set by the caller's router
  )
  set_current_node(my_node)                   # contextvar, for in-process nesting

OUTBOUND (router.invoke_skill, when I delegate):
  ctx2 = current_delegation_context().descend(target_agent_id)   # hop_count+1, visited += me
  # the callee will register itself with parent = my current node:
  ctx2.caller_node_id = current_node()
  dispatch(message_with(ctx2))
  on first stream event: task_graph.link_child(current_node(), event.taskId)  # populate waiting_on
  # status/artifact events → task_graph.update_own_state(child) → reconcile percolates upward
```

Key points:

- **Each agent registers its *own* node** keyed by its A2A task id, with `parent_task_id` from the delegation
  context. No agent pre-creates another agent's node.
- The **caller links the child** into its `child_task_ids` when it learns the child's task id from the first stream
  event. Until then the caller's node is `working` on its own account; once linked, percolation reflects the child.
- `begin_turn`/`finish_turn` (the client-agent's turn bracketing) becomes a **thin special case**: the root node is
  just a node with no delegation context (no caller), created by the client-agent's planner entry point.
- `request_background`/`background_event` (proactive detach) **stay turn-scoped on the client-agent side** — detach
  is a user-facing decision about *the user's* turn, not something a depth-3 agent decides for the whole tree. A deep
  agent that's slow percolates "working — waiting on X"; whether to hand control back to the user is the root's call.

> **Open detail — node-identity handshake.** The "caller links child on first event" model avoids pre-minting ids,
> but has a brief window where the child exists (registered by the callee) before the caller links it. That's fine
> for percolation (the caller is `working` regardless) but should be nailed down: confirm the callee's
> `parent_task_id` and the caller's `child_task_ids` always converge, and decide whether to carry a `delegation_id`
> for joining when task ids are slow to surface.

---

## Q: How do agents wait on each other?

Two cases, very different difficulty — **deliver them separately.**

### Blocking join (near-term; mostly works)

A calls B via the router and `await`s the result. Percolation already keeps A's node `working` with `waiting_on=[B]`,
so the user sees "waiting on B (…)". This is the common case; once specialists can delegate, this is essentially done.
The deep agent blocking on a peer is exactly the prompt's "first agent has to wait and won't answer immediately" —
and the root percolates the deepest blocking leaf's message.

### Non-blocking fork/join (later epic; the hard one)

A dispatches B, *continues or returns*, and later needs B's result. This needs two things we don't have:

1. **Durable continuations** — A's mid-execution state persisted (a `ContextStateStore`) so A can be **re-entered**
   when B completes. A is a request-scoped executor today; "resume A" has no mechanism.
2. **A wakeup + re-attach** — the `tasks:events` channel is the signal, but restart-survivable re-attach wants
   `tasks/resubscribe`, which **LiteLLM does not forward** (the single long-pole; see `background-tasks.md`).

Recommendation: **build blocking delegation first.** Most "deep hierarchy" value is reachable with blocking calls +
the existing detach/percolation. Treat async fork/join as a distinct epic, scoped after the LiteLLM passthrough
decision.

---

## Q: How do we pass context to subagents?

The discipline that matters:

- **`conversation_id` / `contextId`** — the stable scoping key, shared by every agent in the conversation. This *is*
  how a subagent inherits context: all conversation-scoped state (artifact registry, Task Graph, status) keys off it.
  Pass it on every call (already done).
- **`skillId`** — selects the capability (already done).
- **Delegation context** — `origin_agent_id, caller_agent_id, caller_node_id, delegation_id, hop_count,
  visited_agents, visited_skills` — in message **metadata** (location is an open decision: parts vs context metadata
  vs Prometheus header set). Drives loop detection, parentage, and audit.
- **Artifacts: by reference, never by value.** A subagent gets the parent's artifacts by sharing `conversation_id`
  and resolving `artifact_id` / `deeplynx://` URIs through the shared `ArtifactRegistry`
  (`resolve_artifact_reference` already exists). Do **not** inline large payloads into A2A messages.
- **What you deliberately do *not* pass:** the parent's LLM scratch / conversation history. Subagents are *skill
  invocations with explicit params + a shared artifact catalog*, not shared working memory. Keep that boundary —
  it's what keeps delegation auditable and cache-friendly.

> **Open hard problem — `input_required` bubbling.** The `INPUT_REQUIRED` pattern (see repo notes) handles
> client→agent. A question raised by a depth-3 agent must route back *through the chain* to the frontend, and the
> answer back down. Percolation propagates *status*, not the interactive Q&A round-trip. Needs design — likely the
> question becomes an artifact/event on the conversation that the client-agent surfaces, and the answer is delivered
> as a follow-up `message/send` with the original `taskId`/`contextId` to resume the waiting chain.

---

## Decided vs. open

**Decided (this note + the two source docs):**

- Split the orchestrator: **router + Task Graph writer → base class; planner stays in client-agent.**
- Task Graph is shared conversation-scoped substrate; **router writes, client-agent presents.**
- Each agent registers its own node with `parent_task_id` from the wire-carried delegation context.
- Delegation via `self.agent_router.invoke_skill`, through LiteLLM, with hop/loop limits and proxy-owned auth.
- Artifacts by reference; `conversation_id` is the context key; no shared LLM memory.
- **Blocking delegation first; async fork/join is a separate later epic.**
- Proactive detach stays a turn-scoped (client-agent) decision, not a deep-agent one.

**Open — resolve before building distributed hierarchies:**

1. **Node-identity handshake** (caller `child_task_ids` ↔ callee `parent_task_id` convergence; carry a
   `delegation_id`?).
2. **Non-blocking fork/join**: durable continuations + re-entry — biggest unknown, partly LiteLLM-blocked.
3. **`input_required` bubbling** through a multi-hop chain.
4. **Downstream auth ownership** in LiteLLM (single internal token vs per-agent).
5. **Delegation-metadata location** (message parts vs context metadata vs header set).

---

## Phasing (aligns the two plans)

| Step | Deliverable | Depends on |
|---|---|---|
| 1 | Extract transport/discovery into `prometheus_api` router; client-agent uses it as a wrapper | routing-refactor Phases 1–3 |
| 2 | **Move `task_tracking` into the router**; client-agent's turn bracketing becomes the no-caller special case | step 1 + base-image roll |
| 3 | Enable one specialist → peer delegation (blocking), gated; nodes appear in `/tasks` with correct depth | steps 1–2; routing Phase 4 |
| 4 | `input_required` bubbling through a chain | step 3 |
| 5 | Non-blocking fork/join: `ContextStateStore` + re-entry | LiteLLM `tasks/resubscribe` decision |

Steps 1–3 are reachable on the **current LiteLLM** (only `message/send`/`message/stream` needed). Steps 4–5 are the
deep end; 5 is gated on extending LiteLLM's A2A passthrough.
