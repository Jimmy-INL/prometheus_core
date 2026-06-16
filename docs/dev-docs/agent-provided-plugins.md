# Agent-Provided Visualization Plugins

Status: **design**
Owner: platform
Related: [`visualization-plugins.md`](../docs/dev-docs/visualization-plugins.md) (current built-in plugin system),
[`architecture.md`](../docs/dev-docs/architecture.md), [`prometheus_api_a2a_routing_refactor_plan.md`](./prometheus_api_a2a_routing_refactor_plan.md)

## Goal

Let a specialist agent ship its **own** artifact viewer so a new agent can introduce a new `json_type` *and*
the UI that renders it **with zero frontend code changes and no frontend rebuild**. Today a viewer is
`frontend/plugins/<name>/` (Python `render_artifact` + a `.jsx`) baked into the frontend image and dispatched
by `json_type`/`mime_type` (see `visualization-plugins.md`). We want that contribution to come from the agent
instead.

## Core principles

1. **Declarative, not executable, on the server.** An agent contributes *a data type + a React view*, never
   Python that runs in the frontend. Prop mapping is declarative (default `{data: json_body, …}`).
2. **Untrusted-by-default rendering.** Agent JSX is **arbitrary code in the user's browser**. It runs inside a
   **sandboxed iframe** (null origin, no network), never in the Chainlit app context. This is the whole
   security model and is assumed from day one — not bolted on later.
3. **Routing invariants preserved.** The frontend never talks to agents directly; the **client-agent** is the
   aggregator. LiteLLM stays the proxy for *A2A traffic* and is **not** in the JSX path (see next section).

## Routing fact: LiteLLM does not proxy `.well-known/*`

LiteLLM's A2A gateway is **path-routed**: it forwards only `message/send` (and `message/stream` via the
JSON-RPC body) under `/a2a/{agent}`. It does **not** proxy arbitrary paths such as `/.well-known/viewers/*`.

This is already how agent **cards** are fetched: `tool_discovery.get_agent_card` hits the agent's **direct
URL** (`{direct_url}/.well-known/agent.json`) on the shared Docker network — explicitly *because* LiteLLM's
`/a2a/{agent}` response drops metadata. So viewer JSX follows the same path:

```
agent (direct URL, well-known)  ──fetched by──▶  client-agent (aggregates + caches + re-serves)
                                                        │  /viewers/catalog  (+ /viewers/<id>.jsx)
                                                        ▼
                                                   frontend (pulls catalog; renders in sandbox)
```

The client-agent already exposes custom HTTP endpoints the frontend calls directly (`/workflows/catalog`,
`/uploads/stage`, `/discovery/refresh`); `/viewers/catalog` joins them. The frontend never reaches an agent.

## Architecture — three pieces

### 1. Agent declares a viewer (in its agent card)

```jsonc
"viewers": [{
  "json_type": "myagent.result.v1",
  "component": "MyAgentViewer",                 // default export name in the JSX
  "version": "1.2.0",                            // for cache-busting / pinning
  "jsx_path": "/.well-known/viewers/MyAgentViewer.jsx",  // served by the agent at its direct URL
  "props": {"data": "$.json_body", "title": "$.name"}    // optional; default {data, name, description, json_type}
}]
```

The agent serves the JSX file at `jsx_path` on its own HTTP server (a few lines on the `PrometheusAgent` base
class: a static route + a `register_viewer(...)` helper). The base class can also inject the `viewers` array
into the served agent card.

### 2. Client-agent aggregates a viewer catalog

During discovery (it already fetches every card from direct URLs), the client-agent:

- reads each card's `viewers`;
- fetches each `jsx_path` (direct, **not** via LiteLLM), computing a **content hash**;
- caches `{json_type → {component, version, hash, source, props, agent_id}}` in Redis (conversation-agnostic,
  TTL'd);
- exposes `GET /viewers/catalog` (metadata + source) and, if preferred, `GET /viewers/{hash}.jsx`.

Aggregating here (not in the frontend) keeps the "frontend never contacts agents" boundary and reuses the
existing direct-fetch path.

### 3. Frontend renders in a sandboxed iframe

The frontend pulls `/viewers/catalog` on chat-start / discovery-refresh and builds a runtime registry
`json_type → viewer` layered over the static `_json_type_registry` (built-ins win on conflict). When
`render_artifacts` meets an artifact whose `json_type` matches an agent viewer, it does **not** install the
agent JSX as a Chainlit element. Instead it renders **one trusted, frontend-owned element** —
`SandboxedViewer` — passing the agent's component source + the mapped data as props. `SandboxedViewer` hosts
the untrusted code in an isolated iframe (below).

This means: **no runtime writes to `public/elements/`, no per-agent `cl.CustomElement`.** The only custom
element is the trusted `SandboxedViewer`; agent code is *data* passed into the sandbox.

## The sandbox (postMessage protocol) — the heart of the design

`SandboxedViewer.jsx` (trusted, frontend-owned) creates:

```html
<iframe sandbox="allow-scripts" csp="default-src 'none'; script-src 'unsafe-inline' <bootstrap>; style-src 'unsafe-inline'">
```

Critical attributes:

- **`sandbox="allow-scripts"` *without* `allow-same-origin`** → the iframe runs at a **null/opaque origin**: no
  access to the parent DOM, cookies, `localStorage`, the Chainlit session, or same-origin requests.
- **Strict CSP with no `connect-src`** (`default-src 'none'`) → the agent component **cannot `fetch`/exfiltrate**
  the data it is shown. This is the second half of the model: the sandbox stops DOM/credential access; the CSP
  stops network exfiltration. Both are required.

The iframe loads a **trusted bootstrap** (frontend-owned HTML+JS, bundled — React pinned, a JSX transform such
as a prebuilt compile step or Babel-standalone). The bootstrap and parent speak a fixed `postMessage` protocol:

```
parent → iframe:  { type: "render", source: "<agent JSX>", props: {...mapped data}, version }
iframe → parent:  { type: "ready" }
iframe → parent:  { type: "resize", height }          // parent sizes the iframe; no parent-DOM access
iframe → parent:  { type: "action", name, payload }   // optional, allow-listed callbacks (e.g. "open artifact")
parent → iframe:  { type: "props", props: {...} }      // live updates (e.g. streaming)
```

Data minimization: **only the mapped artifact data** is posted into the iframe — never the session, token, or
other artifacts. The parent validates `event.origin`/`event.source` and ignores any message shape outside the
protocol. Actions are an allow-list the parent interprets; the iframe can request, not perform, host actions.

Compilation: agent ships JSX *source*; the bootstrap transforms+mounts it. (Alternative: agents ship
pre-compiled ESM to avoid shipping a transformer — a size/safety tradeoff to decide in phasing.)

## The contract (and one footgun)

JSX authoring rules, documented and **validated at registration**:

- **Default export**, named per `component`.
- **Use the injected `props` (sandbox passes props in); do NOT declare a function parameter `props`.** This is
  the exact bug that made the built-in `CollapsibleJson` render "(no data)" — a `function X(props)` parameter
  shadowed the injected global. The validator should reject a default export that takes a positional arg.
- No imports beyond the bootstrap-provided surface (React + a small allow-listed set). No raw network (the CSP
  enforces this regardless).

A `make`-time / registration-time validator (lint the JSX, check the export + no-param rule + size cap) keeps
bad viewers out before they reach a user.

## Dispatch & registry changes (frontend)

- Generalize `plugins/__init__.py`: add a **runtime `json_type → viewer` layer** populated from the catalog,
  consulted by `find_plugin_for_artifact` after the static registry (built-ins win).
- In `message_handler.render_artifacts`, the agent-viewer branch builds
  `cl.CustomElement(name="SandboxedViewer", props={source, props: mapped, json_type, version})` instead of a
  per-agent element. The existing generic-JSON fallback (`CollapsibleJson`) stays as the default when no viewer
  matches.

## Security model

| Threat | Mitigation |
|---|---|
| Agent JS reads session / cookies / `localStorage` | iframe `sandbox="allow-scripts"` *without* `allow-same-origin` → null origin, no access |
| Agent JS reaches the parent DOM / other artifacts | iframe isolation; parent posts only the one artifact's mapped data |
| Agent JS exfiltrates the data it sees | CSP `default-src 'none'` (no `connect-src`) → no outbound requests |
| Spoofed / tampered viewer | content-hash pin + `version`; namespace by `agent_id`; client-agent fetches over the trusted direct URL; audit-log every registration |
| Malicious `postMessage` into the parent | parent validates `event.source === iframe.contentWindow` and the message schema; actions are an allow-list |
| Resource abuse (infinite loop, huge DOM) | iframe is disposable; consider a render timeout + size cap; one iframe per viewer |

Because isolation is structural (iframe + CSP), this model is safe enough to accept **untrusted / third-party**
agent viewers, not just internal ones — which is the reason to build the sandbox from the start rather than an
in-app render we'd have to retrofit. A coarse `AGENT_PROVIDED_VIEWERS_ENABLED` flag (default off until proven)
and an optional per-agent allowlist remain as operational controls.

## Versioning, namespacing, caching

- Catalog entries keyed by `json_type`; collisions resolved built-ins → first-registered agent, with a warning.
- Component identity namespaced by `agent_id` to prevent spoofing across agents.
- Cache by **content hash**; a `version` bump or hash change invalidates. The frontend can cache the bootstrap
  aggressively (it's trusted and stable) and the agent source by hash.

## Phasing

| Phase | Deliverable | Scope |
|---|---|---|
| 1 | Trusted `SandboxedViewer` element + bootstrap + postMessage protocol + CSP; render a **built-in** viewer through it (prove isolation, resize, data-in) | frontend only |
| 2 | Runtime `json_type → viewer` registry + `render_artifacts` dispatch to `SandboxedViewer`; **artifact-embedded** viewer source (smallest end-to-end: one debug agent ships a viewer inline) | frontend |
| 3 | Agent card `viewers` + base-class `register_viewer`/static route; client-agent `/viewers/catalog` aggregation (direct fetch + hash + Redis cache); frontend pulls catalog | base image + client-agent + frontend |
| 4 | Registration-time JSX validator (export + no-param rule + size cap); content-hash pinning; per-agent allowlist; audit logs | all |
| 5 | Pre-compiled ESM option; live `props` updates for streaming artifacts; allow-listed host actions | frontend |

Phases 1–2 need no base-image roll and no agent changes (a built-in / inline viewer proves the sandbox).
Phase 3 is where agents actually contribute and needs the base-class change (→ base-image roll) plus the
client-agent endpoint.

## Open decisions

1. **JSX source vs pre-compiled ESM** shipped by agents (ship a transformer in the bootstrap, or require agents
   to pre-build). Affects bootstrap size and the validator.
2. **Bootstrap transform**: Babel-standalone (flexible, heavy) vs a fixed compile step vs ESM-only.
3. **Host actions**: which `postMessage` actions (if any) a viewer may request in v1 (open artifact, copy,
   download) — start with none, add by allow-list.
4. **Catalog freshness**: pull on chat-start only, or also on `discovery/refresh`; per-conversation vs global
   cache scope.
5. **`AGENT_PROVIDED_VIEWERS_ENABLED` default** and whether an allowlist is required in the first rollout.
