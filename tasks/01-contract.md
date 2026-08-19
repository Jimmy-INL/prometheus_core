# 01 — Freeze the wire contract (critical path)

> **Status: ✅ Done** (2026-08-10) — `app/contract.py` and `CONTRACT.md` created;
> `frontend-react/AGENT-CONTRACT.md` now points at the new spec.
>
> **Models frozen:** `ChatStatus`, `ChatMessageRequest`, `ChatMessageResponse`,
> `FormField` + `SelectOption` + `normalize_followup_questions()` (ported from
> `_handle_needs_info`), `ArtifactMeta` + `RenderHint`, `UploadDescriptor`, the SSE
> `ServerEvent` union (`StatusEvent`/`TaskProgressEvent`/`TaskDoneEvent`), plus
> `SessionResponse`/`ConfigResponse` for tasks 02/08.
>
> **Verification:** `ruff check` + `mypy` clean; round-trip test builds all 8 response
> variants + request + SSE events, `.model_dump_json()` → re-parse with no loss, and
> confirms the discriminated union resolves each event to its concrete type and `status`
> serializes as a plain string.
>
> **Open questions resolved:** `render_hint` is emitted (classifier output) with raw
> `mime_type`/`json_type`/`tags` retained for frontend override; SSE session = auth JWT
> session id; `POST /api/sessions` is explicit (`SessionResponse`).

## Goal

Define `app/contract.py`: the Pydantic models for our request, our response, the SSE event
schema, the DynamicForm field schema, and the artifact-metadata shape. This is the interface
the React follow-up will code against, so freezing it early unblocks parallel work.

## Files to create

- `chat-backend/app/contract.py`
- `chat-backend/CONTRACT.md` — human-readable spec (supersedes the Chainlit-flavored
  `frontend-react/AGENT-CONTRACT.md` for the new API; link from it).

## Models to define

### Request — `ChatMessageRequest`
Mirrors the fields `A2AClient.send()` accepts (see `frontend/utils/a2a_client.py:81`):
`query: str`, `followup_answers: dict | None`, `plan_approved: bool = False`,
`plan_rejected: bool = False`, `workflow_id: str | None`, `upload_ids: list[UploadDescriptor] | None`.
`conversation_id` comes from session state, **not** the request body.

### Response — `ChatMessageResponse`
`{turn_id: str, status: ChatStatus, message: str | None, ...}` with status-specific optionals.
`ChatStatus` = literal set mirroring `ConversationStatus`: `needs_info | plan_ready |
executing | completed | answer | recommendation | error | backgrounded`. Fields:
- `followup_questions: list[FormField] | None` (for `needs_info`)
- `plan: dict | None`, `auto_approve: bool` (for `plan_ready`)
- `report: str | None`, `response_text: str | None`, `artifacts: list[ArtifactMeta] | None`,
  `recommended_materials: list[str] | None`, `follow_up_suggestions: list[str] | None`
  (for `completed`/`answer`/`recommendation`)
- `task_id: str | None` (for `backgrounded`)

### `FormField` (DynamicForm schema)
Match what the React `DynamicFormElement.tsx` expects and what `_handle_needs_info` produces:
`id`, `label`, `input_type` (text/number/email/password/date/datetime/textarea/select/checkbox),
`required: bool = True`, `options: list[{label,value}] | None`, `default`, `help`,
`placeholder`, `rows`, `min`, `max`, `step`. Include the normalization mapping from raw
`followup_questions` (see `_handle_needs_info` field-building loop, message_handler.py ~502–518).

### `ArtifactMeta`
`artifact_id`, `name`, `mime_type`, `json_type`, `description`, `uri`, `tags`,
`json_body` (inline only), `render_hint` (see task 07 classification),
`producer_agent_id`, `created_at`. Snake_case (Prometheus catalog convention — see
`docs/docs/dev-docs/artifacts.md`).

### `UploadDescriptor`
`{upload_id, name, mime_type, size_bytes}` — returned by `POST /api/uploads`, echoed back in
the next `ChatMessageRequest`.

### SSE events — discriminated union on `type`
- `StatusEvent`: `{type: "status", turn_id, message, history: list[str] | None}`
- `TaskProgressEvent`: `{type: "task_progress", task_id, message}`
- `TaskDoneEvent`: `{type: "task_done", task_id, state, response: ChatMessageResponse | None}`
- Plus a `heartbeat` comment line (`: ping`) — not a JSON event.

## Acceptance check

- `contract.py` imports cleanly; `uv run mypy` passes.
- A round-trip test: build each response variant, `.model_dump_json()`, re-parse — no loss.
- `CONTRACT.md` documents every endpoint payload with a JSON example per status.

## Open questions to resolve here (from the plan)

- **`render_hint` vs raw metadata** — default: emit `render_hint` (classifier output). Keep
  raw `mime_type`/`tags`/`json_type` too so the frontend can override.
- **Session identity** — reuse the auth JWT's subject/session id as the SSE session token.
- **`POST /api/sessions`** — explicit session creation (not implicit-on-first-message).
