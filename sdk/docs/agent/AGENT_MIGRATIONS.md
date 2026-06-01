# Prometheus Agent Migration Guide

This document is the running migration log for `PrometheusAgent` behavior changes.
When a base-agent change requires downstream agent updates, add a short section here
with migration steps and a minimal code example.

## Use the Agent `_execute` Hook

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

## Build Apps Through `build_app`

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

## Configure Required Auth Explicitly

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

## Let Startup Handle Registry Registration

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

## Use Status Helpers Instead of Manual Events

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
