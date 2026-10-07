# Glossary

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

- **A2A.** Agent-to-Agent protocol 1.0: JSON-RPC `SendMessage`, `SendStreamingMessage` on `POST /`. Old `message/send` fails with `-32601`.
- **Agent.** A `PrometheusAgent` subclass that does skills. You write `_execute(params, context, event_queue)` (`agent-code.md`).
- **Agent card.** `agent_card.json`: name, description, capabilities, skills. Served at `GET /api/agent-card` (`card.md`).
- **Artifact.** A file or data result with an `artifact_id`, in the conversation's catalog (7 days). Pass ids, not data.
- **`ask_user`.** The orchestrator's tool for an open question; the turn ends `needs_info`.
- **Background task.** Work after the turn ends, from `declare_long_running`; `/tasks` shows it (`long-running.md`).
- **Base image.** `containers.github.inl.gov/genesis/prometheus_api:<tag>`. It holds the SDK (`environment.md`).
- **`contextId`.** The conversation id: `context.context_id` in your code.
- **Context state.** Per-agent, per-conversation JSON: `save_context_state`, `load_context_state`; 24 hours.
- **DeepLynx.** INL's data store for uploads and result files (`deeplynx://...`). No DeepLynx, no uploads or PNGs.
- **Discovery.** The client-agent reads the registry, fetches each card, and caches it 60 s (`run-and-register.md`).
- **Flavor.** The LLM kind you ask for: `default`, `small`, `medium`, `large`, `vision`, `embedding` (`llm.md`).
- **`inputSchema`.** A skill's parameters as JSON Schema; the LLM gets it without `x_*` keys.
- **Input-required.** `send_input_required` pauses the task; `_execute` runs again with the answers.
- **LiteLLM.** The registry, the A2A gateway (`/a2a/<route key>`), and the LLM proxy; container `litellm-proxy`, port 9977.
- **`LLMClient`.** The LLM interface: `self.llm_client(context, config=cfg)`.
- **Secrets.** `AGENT_SECRET` (LiteLLM's token to each agent) and `LITELLM_MASTER_KEY` (the registry and the LLM proxy).
- **Orchestrator.** The `client-agent`: an LLM loop that calls skills and chains the results.
- **Pin / profile.** The `prometheus_api` commit the platform builds from (`environment.md`); `LLM_CONFIG_PROFILE` maps flavors to models (default `registry`).
- **Registry.** LiteLLM. Agents register at startup; a platform `make up` or `make restart` empties it.
- **`requires_approval`.** A skill field: the user approves first; the turn ends `plan_ready`.
- **Route key.** The card name, lowercase, spaces to hyphens. A second agent with the same key replaces the first.
- **Signing key.** The RS256 key for each turn's `userToken`. Admin › Signing Keys: generate, then activate.
- **Skill / skill id.** One thing an agent does; one tool. The id: `[a-zA-Z0-9_-]`, at most 64, unique; it arrives as `params["skill_id"]`.
- **Status update.** A `send_status_update` line; it shows live only with `capabilities.streaming: true`.
- **`usage_notes`.** Shown to the LLM as `Usage: <usage_notes>`: when to use the skill, and when not.
- **Valkey.** The state store: service `redis`, container `agent-valkey`, port 6379.
- **Workflow.** A YAML template that chains skills; a `workflow_*` tool and a slash command (`workflows.md`).
- **`x_artifact_ref`, `x_input_source: runtime`.** Marks on a property: an artifact id; a value that another skill makes.
