# Plan: Replace Chainlit with a Standalone FastAPI Chat Backend

> Reconstructed 2026-08-10 from the original `/plan` project brief (session Aug 6).
> The synthesized implementation plan from that session was never saved; this document
> restores the brief and turns it into an actionable, ordered plan.

## Goal

Build a FastAPI service that fully replaces the Chainlit 2.10 deployment. **Big-bang
cutover** — the frontend is being rebuilt in-house in parallel (`frontend-react/`), so we
define our own API contract with **no Chainlit protocol compatibility**. All `chainlit`
imports are removed.

## What the current app actually is

The Chainlit app (`frontend/`) is a **thin client over a separate A2A agent service**. No
LLM logic lives in it. Chainlit currently provides:

1. **Auth** — password (`local_users` from settings) with an OAuth stub for later.
2. **Turn orchestration** — forwarding queries to `A2AClient.send()` and dispatching on
   response status: `needs_info`, `plan_ready`, `executing`, `completed`/`answer`/
   `recommendation`, `error`, `backgrounded`.
3. **Server-driven interactive UI** — `cl.Step` live status updates, `AskElementMessage`
   (DynamicForm) for follow-up questions, `AskActionMessage` for plan approval,
   `CustomElement`s (PlanViewer, FollowUpSuggestions, CollapsibleJson).
4. **Out-of-band push** — a per-session Redis subscriber (`run_task_notifier`) that posts
   progress and results of backgrounded tasks after the original request has returned.
5. **File upload** — size-limited uploads, plugin-based preview, staging to DeepLynx via
   the agent.
6. **Artifact rendering** — resolving `deeplynx://` / remote URIs and rendering PDFs, JSON,
   reports, downloads.
7. **Session state** — `conversation_id`, artifacts catalog, awaited background-task ids,
   chat profile.
8. **Chat profiles** — Beginner (intro + suggestions) vs Advanced.

## Architecture decisions

### D1. Invert the interaction loop (biggest change)

Today the server *blocks awaiting UI input* (`AskElementMessage`, `AskActionMessage`) and
recurses on `needs_info`. This exists only because Chainlit allows it. New model: the API
**returns** the agent's status + payload; the **frontend** renders the form or
plan-approval UI; the user's answer is simply the next `POST /api/chat/messages` carrying
`followup_answers`, `plan_approved`, or `plan_rejected` — fields `A2AClient.send()` already
accepts. Consequences:

- No blocking server-side waits, no timeouts, no `_MAX_NEEDS_INFO_DEPTH` recursion.
- The backend becomes a near-stateless proxy/orchestrator around A2AClient.
- Follow-up-depth limiting (if still wanted) becomes a frontend concern.

### D2. One persistent SSE events channel per session

Because backgrounded tasks complete after the originating request returns, per-request
streaming is not enough. Provide:

- `GET /api/events` — long-lived SSE stream, one per browser session. Carries typed events:
  - `status` — live progress during an in-flight turn (replaces `cl.Step` updates;
    includes turn id + message, frontend keeps the history list).
  - `task_progress` / `task_done` — background task updates and terminal results (replaces
    `run_task_notifier` + `_maybe_announce_completion`, including the fast-finish/
    idempotency guard — keep the "consume the awaited id once" semantics server-side).
- `POST /api/chat/messages` — sends the turn; returns the agent's terminal response for that
  turn as JSON (status + payload). Status updates during the turn flow over `/api/events`
  keyed by a turn id the POST response also carries.

The events endpoint owns the Redis subscription (one per connected session), filtered to
root task ids the session is awaiting — port the root-vs-child filtering logic from
`run_task_notifier`.

Nginx: `proxy_buffering off` and long `proxy_read_timeout` on `/api/events`.

### D3. Rendering moves to the frontend; backend keeps a content proxy

The bulk of `message_handler.py` (`render_artifacts` and friends) converts artifacts into
Chainlit elements. Instead:

- API returns artifact **metadata** (name, mime_type, json_type, description, uri,
  artifact_id, json_body when inline).
- Frontend ports PlanViewer, DynamicForm, FollowUpSuggestions, CollapsibleJson as ordinary
  React components consuming JSON.
- Backend keeps `GET /api/artifacts/{artifact_id}/content` which performs `deeplynx://`
  resolution (`resolve_to_local_path`) and remote fetches, streaming bytes with correct
  MIME — this replaces `_render_pdf_artifact`, `_render_remote_file_artifact`,
  `_render_download_artifact`.
- The classification logic (`_classify_artifact`) can ship to the frontend or be returned
  as a `render_hint` field — decide during contract design.
- Visualization plugins: the `plugins` package currently produces JSX + Chainlit elements.
  Decide per plugin whether its output becomes (a) frontend components fed by metadata, or
  (b) a backend preview endpoint. Inventory the plugins as an early task.

### D4. Session and state

- Auth: password login against `settings.local_users`, JWT in httpOnly cookie. Pluggable
  identity-provider interface so the existing OAuth stub becomes a real provider later
  (`GET /api/auth/callback/{provider}` reserved).
- Per-session state (in-memory, keyed by session id): `conversation_id`, artifacts catalog,
  awaited background-task ids, chat profile. No thread persistence (unchanged). Note: state
  is lost on API restart — same as today.
- `POST /api/sessions` (or implicit on first message): creates `conversation_id`, returns
  chat-profile config and intro content (replaces `on_chat_start` / `set_chat_profiles`).
  Frontend chooses profile at session start.
- `/history` slash command → `GET /api/conversations/recent` reading from
  `ConversationStateClient` (Redis); frontend renders the list. Slash-command parsing moves
  to the frontend.

### D5. File uploads

In scope (staging-to-DeepLynx flow is used). `POST /api/uploads` (multipart):

- Enforce `MAX_UPLOAD_BYTES`; keep CAD MIME mapping (`_guess_upload_mime`).
- Run plugin inspection (`inspect_upload`) if server-side previews are kept; otherwise
  return metadata for frontend preview.
- Stage via `A2AClient.stage_upload`, return `{upload_id, name, mime_type, size_bytes}`.
- Frontend includes the returned upload descriptors in the subsequent
  `POST /api/chat/messages`.

### D6. Dropped

- Socket.IO, `/set-session-cookie`, `/feedback`, `/mcp`, `/chainlit/`, `/public/` static
  serving, `on_settings_update` debug options (re-add as `PATCH /api/session/settings` only
  if the new frontend needs it).

## API surface (v1)

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` / `POST /api/auth/logout` / `GET /api/auth/me` | Password auth, session cookie |
| `POST /api/sessions` | Start session: conversation_id, profile, intro/suggestions |
| `POST /api/chat/messages` | Send turn (query, followup_answers, plan_approved/rejected, upload ids) → agent response JSON |
| `GET /api/events` | SSE: status, task_progress, task_done |
| `POST /api/uploads` | Stage file, return upload descriptor |
| `GET /api/artifacts/{id}/content` | Resolve + stream artifact bytes |
| `GET /api/conversations/recent` | Redis-backed history list |
| `GET /api/config` | Chat profiles, suggestions, limits (from settings) |
| `GET /healthz` | Liveness |

## Response contract (sketch — formalize first)

`POST /api/chat/messages` returns `{turn_id, status, message, ...}` where status-specific
payloads mirror `ConversationResponse`:

- `needs_info`: `followup_questions` (normalize to the DynamicForm field schema
  server-side, reusing the mapping in `_handle_needs_info`)
- `plan_ready`: `plan` (+ `auto_approve` flag from settings so the frontend knows whether
  to show buttons)
- `completed`: `report/response_text`, `artifacts` (metadata + render hints),
  `recommended_materials`, `follow_up_suggestions`
- `backgrounded`: `task_id` (server registers it as awaited)
- `error`, `executing`: message

## Work plan (ordered)

1. **Contract doc.** Freeze the JSON shapes above + SSE event schema with the frontend
   team. Include the DynamicForm field schema and artifact metadata shape. This is the
   critical path for parallel work.
2. **Plugin + element inventory.** List every `CustomElement`/plugin in use; assign each to
   frontend-rendered vs backend-preview. Determines frontend scope.
3. **Skeleton + auth.** FastAPI app, healthz, login/logout/me, cookie sessions,
   identity-provider abstraction, `/api/config`, `/api/sessions`.
4. **Chat turn path.** Port `message_handler`'s orchestration (minus rendering, minus
   blocking waits) into a service: A2AClient call with `on_status` publishing to the
   session's event queue; status→response mapping.
5. **Events channel.** SSE endpoint + per-session Redis subscriber, porting
   `run_task_notifier` semantics (root-task filtering, idempotent announce, fast-finish
   guard, progress history limit).
6. **Uploads + artifact content proxy.** Port size limits, MIME logic, `stage_upload`,
   `resolve_to_local_path`.
7. **History endpoint.** Wrap `ConversationStateClient`.
8. **Docker + nginx.** New container; nginx serves frontend at `/`, proxies `/api/`, SSE
   tuning on `/api/events`.
9. **Verification + cutover.** Test matrix across every status path; remove the
   `chainlit-frontend` service and all `chainlit` imports.

## Key source references (Chainlit side, to port from)

- `frontend/main.py` — `on_chat_start`, `set_chat_profiles`, auth callback, session state.
- `frontend/components/message_handler.py` — turn orchestration, `render_artifacts`,
  `_classify_artifact`, `_handle_needs_info`, `_render_pdf_artifact` /
  `_render_remote_file_artifact` / `_render_download_artifact`, `run_task_notifier`,
  `_maybe_announce_completion`.
- `frontend/utils/a2a_client.py` — `A2AClient.send()` (accepts `followup_answers`,
  `plan_approved`/`plan_rejected`, upload ids), `stage_upload`, `resolve_to_local_path`;
  re-exports contract types from `prometheus_api.contract`.
- `frontend/plugins/` — plugin Python wrappers producing JSX/Chainlit elements.
- `frontend/public/elements/` — PlanViewer, DynamicForm, FollowUpSuggestions, MeshViewer,
  IFCViewer, MermaidViewer (React/JSX to port to `frontend-react/`).
- `frontend/config.yml` — `agent-url`, `agent-secret`, `redis-url`, `auto-approve-steps`,
  `local-users`, workflow suggestions.

## Contract types (source of truth)

`ConversationRequest`, `ConversationResponse`, `ConversationStatus` live in
`prometheus_api.contract` (the `prometheus_api` repo, baked into the base image). The new
FastAPI response contract mirrors `ConversationResponse` but is defined independently — do
**not** couple the wire format to Chainlit types.

## Open questions to resolve during contract design

- `_classify_artifact` on frontend vs `render_hint` field returned by backend? (D3)
- Which plugins become frontend components vs backend preview endpoints? (task 2)
- Keep server-side follow-up-depth limiting or drop entirely? (D1)
- Session identity: reuse auth JWT session id, or separate SSE session token?

## Notes on current repo state (2026-08-10)

- Branch `old-frontend-removal`; in-flight changes to `docker-compose.yml`, `Makefile`,
  `.env.example`, and nginx config (`frontend-react/nginx.conf` deleted, `nginx1.conf`
  added). The cutover appears partly underway — **re-verify these decisions against the
  current tree before implementing**, since this plan was reconstructed from an Aug 6 brief.
- `frontend-react/` already exists and (per the Aug 6 exploration) was coupled to Chainlit
  via `@chainlit/react-client`; part of this work is removing that coupling in favor of the
  new API.
