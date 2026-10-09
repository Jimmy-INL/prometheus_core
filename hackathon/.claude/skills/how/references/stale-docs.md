# Stale docs: what older docs say, and what the code does now

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

Trust the code, and tell a mentor (deck 01, slide 12 and A18-A19; deck 04, A3).

| you may read | the code now |
|---|---|
| A Chainlit UI on :8500 | React on :5150, FastAPI backend on :8600 |
| A2A `message/send`, `params.context.skillId` | `SendMessage`, `message.metadata.skillId` (A2A 1.0); `message/send` fails with `-32601` |
| `process_analysis()` | `_execute(params, context, event_queue)` (`prometheus_api/prometheus_api/agent/base.py:1417`) |
| `request_user_approval(...)` | Does not exist: `"requires_approval": true`, or `send_input_required` |
| Log in as `prometheus` / `prometheus` | A setup wizard makes the first admin |
| Base image from `mooseharbor`, pinned in compose | From `containers.github.inl.gov`, pinned in the platform `Makefile:22` |
| `PROMETHEUS_DEBUG`, `planner.py`, the pin `2b3dbcf` (v0.8.0) | `DEBUG_AGENTS=true`; `orchestrator/agent_loop.py`; the pin `95c32b5` |
| A workflow YAML with no `description` | `description` is required (`workflow_library/schema.py:75`) |
| `/v1/agents` with no key, or piped to `json.tool` (decks 03-05) | It needs the master key and prints each `AGENT_SECRET`: print names only (`conventions.md`) |
| `setup_agent.py --help` shows arguments | `main()` ignores them; it is interactive only (`setup_agent.py:389-400`) |
| Host run with `AGENT_SECRET_REQUIRED=false` only | Also `USER_IDENTITY_REQUIRED=false`, else "No 'userToken' found" |

Old text remains in the platform `docs/docs/` pages, the template `TUTORIAL.md` and `README.md`, and
`prometheus_api/docs/agent/MULTI_USER.md`. "Planner tool" means "orchestrator tool".

## The client-agent log does not show the turn

Deck 03, A11 and deck 04, slide 19 say it does. It does not: the status lines go to Valkey and the UI
(`agents/client-agent/orchestrator/runtime.py:139-161`). The log shows discovery prints and errors.
Read the turn from Valkey, or run `/diagnose trace my last chat`.

## The `small` flavor and the `anl_asksage` profile

Deck 04, slides 15-16 use `small`, but `registry` defines only `medium` (`litellm_config.yaml:6-10`): `small`
raises `LLMAliasError`. `anl_asksage` (deck 03, slide 8) is not in the SDK at the pin. More in `llm.md`.
