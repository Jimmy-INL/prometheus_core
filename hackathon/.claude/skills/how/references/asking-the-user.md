# Asking the user

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

The platform asks the user for you. You never parse chat text (deck 04, slides 2 and 21). Short paths:
`base.py` and `context_state.py` are in `prometheus_api/prometheus_api/agent/`; `agent_loop.py` is in
`prometheus_platform/agents/client-agent/orchestrator/`, `tool_discovery.py` one folder up.

| moment | mechanism | you write |
|---|---|---|
| before the call: a required input the LLM cannot fill | a form (`needs_info`) | the card `required` |
| before the call: a costly step | Approve/Reject (`plan_ready`) | the card `requires_approval: true` |
| during the call: choices only your code knows | input-required, then a second call | `send_input_required` and state |

**Form fields** (`agent_loop.py:1092-1100`): an `enum` gives `select`, `number`/`integer` give `number`,
`boolean` gives `checkbox`, all else `text`. The label is `title`; the help is `description`. There is no
multiselect: ask one `select` per value. An `enum` is fixed, so for choices from the data keep the property
optional and use input-required.

**Approval** (`agent_loop.py:582-590`): one call only; the form comes first, then the approval. Example:
`prometheus_platform/agents/debug-agents/corrosion-agent/agent_card.json:15`. `request_user_approval(...)`
does not exist (deck 04, A27).

## Input-required

```python
from prometheus_api.agent import MissingInput

ctx = str(context.context_id)
state = self.load_context_state(ctx)
x = params.get("x_column") or self.get_provided_inputs(context).get("x_column")
if not x:
    columns = ["Year", "Residents"]  # TODO: read the real column names
    self.save_context_state(ctx, {"table_id": params.get("table_artifact_id"), "columns": columns})
    await self.send_input_required(
        context, event_queue,
        missing_inputs=[MissingInput(name="x_column", description="Column for the x axis",
                                     user_prompt="Which column goes on the x axis?", type="enum", options=columns)],
        hint="Choose the columns to plot.",
    )
    return {}
```

1. `send_input_required` ends the task in `TASK_STATE_INPUT_REQUIRED` (`base.py:1033-1068`). Return `{}`:
   the value is ignored.
2. The orchestrator calls you again with the same `contextId`, the same `params`, and the answers in a
   separate part (`tool_discovery.py:475-503`). `get_provided_inputs` returns them (`{}` on the first call).
3. **Python state does not survive.** Save before you ask, load on the resume (deck 04, slide 12). State is
   per agent and conversation, JSON, 24 h TTL (`context_state.py:13-87`). Save ids, not DataFrames.

`MissingInput` (`base.py:103-114`): `name`, `description`, `user_prompt`, `type` (`enum`, `number` →
`float`, `integer` → `int`, `boolean`, else text), `options`, `resolvable_from_context`, `sensitive`,
`required`. An empty answer counts as no answer.

Traps: a typed reply drops the call (`agent_loop.py:745-759`); a `required` input shows the form before
your code runs. Reference: `prometheus_platform/agents/debug-agents/corrosion-agent/agent.py:112-168`.
