# Run and register your agent

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

## Start it

`make up` in the agent folder runs `docker compose up --build -d` and joins
`prometheus_platform_agent-network` (`agent_template/Makefile:71-73`); without the network it
stops with "The Prometheus Platform must be launched first…". The image holds the code and the
card (`agent_template/Dockerfile:34-37`), and Compose reads `environment:` only on create: after
any change, run `make up`, not `docker restart`. `make logs` never ends; use `docker logs`.

## Registration and the route key

At startup the agent deletes an entry with its `agent_name` from `{REGISTRY_URL}/v1/agents`, then
registers its card, URL, and `static_headers` (`Bearer <AGENT_SECRET>`) with the master key
(`prometheus_api/prometheus_api/agent/registry.py:78-165`; deck 04, A15). The log says
`Registered '<route key>' with LiteLLM at http://litellm-proxy:4000`.

- **The route key** is the card `name` in lowercase, spaces changed to hyphens
  (`registry.py:50-53`): "Hello Max Agent" → `hello-max-agent`. The same key deletes the other
  entry (`registry.py:123-130`).
- **Retries**: 2 s, doubled, at most 30 s, 11 attempts, then "Continuing without registration"
  (`registry.py:200-233`). Verify with `agent-registered-log` and `registry-agents` (`checks.md`).

## Discovery: how the orchestrator finds you

The `client-agent` reads `/v1/agents`, fetches your full card from your URL (the LiteLLM copy has
no `inputSchema`, `client-agent/tool_discovery.py:118-143`), and makes one tool per skill. It calls
`POST http://litellm:4000/a2a/<route key>` with `A2A-Version: 1.0`, for up to 900 s. The cards
that the LLM sees refresh every 60 s (`capability_cache.py:96`); the dispatch tools every 300 s
and once on an unknown skill (`orchestrator/runtime.py:209-217`). `discovery-refresh` renews both.

## What to run after a change

| what changed | run |
|---|---|
| code, card, `pyproject.toml`, `Dockerfile`, compose, or the agent `.env` | `make up` in the agent folder, then `discovery-refresh` |
| the platform restarted (it empties the registry, `Makefile:232-250`) | `docker restart <container>`, or `make up` after a `make down` |
| `docker restart` fails: "network … not found" | `make down`, then `make up` |
| any of these, before a chat test | a fresh chat conversation (deck 04, slide 18) |

## Without the platform: the debug route

Run `AGENT_SECRET=dev AGENT_SECRET_REQUIRED=false USER_IDENTITY_REQUIRED=false PROMETHEUS_TASK_STORE=memory python agent.py`
in the venv, then `curl -s -X POST localhost:8000/api/chat -H "Content-Type: application/json" -d '{"params": {"skill_id": "<id>", "person_name": "Marie Curie"}, "conversation_id": "conv-1"}'`.
It runs `_execute` in-process (`agent/debug_routes.py:144-185`; deck 04, A18). On the host, a
`.env` in the folder wins over the environment (`llm_client/config.py:76-87`).

## A2A errors

A real call: `POST /`, `A2A-Version: 1.0`, method `SendMessage`, inputs as JSON text in
`parts[0].text`, and `metadata.skillId` (deck 04, A19).

| error | cause |
|---|---|
| `-32601` Method not found | the v0.3 method `message/send`; v1 uses `SendMessage` |
| `-32009` "A2A version '0.3' is not supported…" | no `A2A-Version: 1.0` header |
| `-32603` with "No 'userToken' found…" | `USER_IDENTITY_REQUIRED=true` and no user token |
| `-32004` "Streaming is not supported by the agent" | `SendStreamingMessage` to a card with `"streaming": false` |
| HTTP 401 | a missing or wrong bearer token (`AGENT_SECRET`) |
