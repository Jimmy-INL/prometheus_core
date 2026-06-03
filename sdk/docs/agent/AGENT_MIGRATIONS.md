# Prometheus Agent Migration Guide

This document is the running migration log for `PrometheusAgent` behavior changes.
When a base-agent change requires downstream agent updates, add a short section here
under the relevant version heading with migration steps and a minimal code example.

## 0.6.0

### Keepalive Heartbeats During `_execute` — Do Not Block the Event Loop

The base executor now emits periodic non-final "working" status events while your
`_execute` runs, so long-running agents keep traffic on the wire and do not trip
upstream idle-connection timeouts (LiteLLM/aiohttp) mid-task.

This only works if your `_execute` does not block the single event loop. A
synchronous call that does not `await` — a blocking SDK
(`anthropic.Anthropic().messages.create(...)`), `requests`, a legacy library, a
CPU loop, `time.sleep` — freezes the loop, so the heartbeat (and your own
`send_status_update` calls) cannot be sent and the very timeout the heartbeat
prevents will still fire. The fix is never a bigger timeout; it is to keep the
loop free.

Migration steps:

1. Audit `_execute` for synchronous, blocking calls and offload them with
   `asyncio.to_thread` (or use an async client). For long blocking work that needs
   to stream progress, use `PrometheusWorker` (below).
2. If you consume or inspect the raw event stream, ignore heartbeat events: they
   carry no message and are tagged `metadata.heartbeat=true`.
3. Tune or disable the cadence with `PROMETHEUS_HEARTBEAT_INTERVAL` (seconds;
   default `15`, `0` disables).

```python
# WRONG — blocks the loop for the whole call; heartbeat and streaming stall
result = blocking_library.run(payload)

# CORRECT — runs off-loop; the loop stays free to flush heartbeats/status
result = await asyncio.to_thread(blocking_library.run, payload)
```

### Run Blocking Workloads with `PrometheusWorker`

For genuinely blocking work that should still stream progress, subclass
`PrometheusWorker` and dispatch it with `PrometheusAgent.run_worker`. The worker's
`run()` executes on a worker thread; from there it cannot touch the loop-bound A2A
event queue, so it emits a safe subset of events into a thread-safe mailbox that
`run_worker` drains and forwards from the loop. Only pure, no-I/O event
construction is exposed — `emit_status_update` and `emit_json_artifact` (inline,
not cataloged). DeepLynx uploads, catalog registration, conversation messages, and
`INPUT_REQUIRED` are intentionally unavailable; do those on the loop, before or
after `run_worker`.

Migration steps:

1. Move the blocking work into a `PrometheusWorker.run()` (plain synchronous code).
2. Stream progress with `self.emit_status_update(...)` and, for verbose output,
   `self.emit_json_artifact(...)` (supports `append`/`last_chunk` for chunks).
3. Check `self.cancelled` periodically and stop early — threads cannot be
   force-killed, so cancellation is cooperative.
4. Dispatch from `_execute` with `await self.run_worker(worker, context, event_queue)`,
   which returns `run()`'s result and re-raises its exceptions.

```python
from prometheus_api.agent import PrometheusAgent, PrometheusWorker


class CrunchWorker(PrometheusWorker):
    def run(self):
        total = len(self.items)
        for i, item in enumerate(self.items, 1):
            if self.cancelled:
                return {"status": "cancelled", "done": i - 1}
            self.emit_status_update(f"Crunching {i}/{total}…")
            heavy_blocking_call(item)
        return {"status": "success", "processed": total}


class CrunchAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        worker = CrunchWorker()
        worker.items = params["items"]
        return await self.run_worker(worker, context, event_queue)
```

## 0.5.0

### Use the Agent `_execute` Hook

Most agents should implement `PrometheusAgent._execute()` and let the base class create
the executor. The executor now delegates to the agent's `_execute` method through
`DelegatingPrometheusAgentExecutor`; downstream agents do not need a custom nested
executor just to run their logic.

Migration steps:

1. Remove custom `create_executor()` methods that only wrap the agent's `_execute`.
2. Keep the existing async `_execute(params, context, event_queue)` implementation on
   the `PrometheusAgent` subclass.
3. Override `create_executor()` only when replacing the standard execution lifecycle.

```python
from prometheus_api.agent import PrometheusAgent


class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Running analysis.",
        )
        return {"message": "Analysis complete.", "agent": self.agent_name}
```

### Build Apps Through `build_app`

Agents that host the Starlette app themselves should call `build_app()` instead of
constructing `A2AStarletteApplication`, request handlers, middleware, and debug routes
manually. This keeps authentication, health routes, debug routes, lifespan hooks, and
registry startup behavior consistent.

Migration steps:

1. Replace manual Starlette/A2A app assembly with `agent.build_app()`.
2. Use `register_on_startup=False` in tests or harnesses that should not contact the
   registry.
3. Put custom routes in `configure_app(app)` and startup/shutdown work in
   `lifespan(app)`.

```python
agent = MyAgent(agent_name="My Agent")

# Production/custom host:
app = agent.build_app()

# Tests:
test_app = agent.build_app(register_on_startup=False)
```

### Configure Required Auth Explicitly

When `AGENT_SECRET_REQUIRED=true` (the default), `AGENT_SECRET` must be configured before
the agent app is built. The base agent fails fast at app construction time instead of
starting a server with unusable authentication middleware.

Migration steps:

1. Set `AGENT_SECRET` for deployed agents.
2. Keep `AGENT_SECRET_REQUIRED=true` outside local unauthenticated development.
3. Set `AGENT_SECRET_REQUIRED=false` only for local tests or demos that intentionally do
   not require bearer-token auth.

```bash
AGENT_SECRET=shared-agent-token
AGENT_SECRET_REQUIRED=true
```

```python
# Local unauthenticated test harness only.
monkeypatch.setenv("AGENT_SECRET_REQUIRED", "false")
app = agent.build_app(register_on_startup=False)
```

### Let Startup Handle Registry Registration

Registry registration now runs as an asynchronous background task from app lifespan
startup. The task keeps exponential backoff retries so an agent can come up while the
LiteLLM registry is still becoming ready.

Migration steps:

1. Remove explicit startup calls to `register_with_registry()` from agent entrypoints
   unless a non-Starlette host truly needs them.
2. Use `agent.run()` or `agent.build_app()` so lifespan startup schedules registration.
3. Use `REGISTRY_MAX_RETRIES` to tune retries after the first attempt.
4. Set `register_on_startup=False` for tests that should not start registration.

```python
if __name__ == "__main__":
    agent = MyAgent(agent_name="My Agent")
    agent.run()
```

```bash
REGISTRY_URL=http://litellm:4000
REGISTRY_MAX_RETRIES=10
```

### Use Status Helpers Instead of Manual Events

Status event construction is centralized so `task_id`, `context_id`, text messages, and
metadata stay consistent across the executor and public helper APIs.

Migration steps:

1. Replace direct `TaskStatusUpdateEvent(...)` progress events with
   `send_status_update(...)`.
2. Keep returning a dict from `_execute`; the base executor emits the final completed
   event automatically.
3. Use `send_input_required(...)` for final input-required responses.

```python
class MyAgent(PrometheusAgent):
    async def _execute(self, params, context, event_queue):
        await self.send_status_update(
            context=context,
            event_queue=event_queue,
            message="Loading source data.",
        )
        return {"message": "Done.", "agent": self.agent_name}
```
