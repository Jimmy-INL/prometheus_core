# 04 — Chat turn orchestration (the inverted loop)

## Goal

Implement the non-blocking turn path: `POST /api/chat/messages` calls `A2AClient.send()`,
streams live status onto the session's event bus via `on_status`, and maps the terminal
`ConversationResponse` to our `ChatMessageResponse`. This is the core of decision **D1**.

## Files to create

- `backend/app/services/chat.py`
- `backend/app/routers/chat.py`

## What to port from `frontend/components/message_handler.py`

*(Source is the now-removed Chainlit app's `frontend/components/message_handler.py` — recover
from git history; ported into `backend/app/services/chat.py`. The `message_handler.py:NNN` line
refs below are relative to that historical file.)*

Port the **logic**, drop the **blocking waits and Chainlit rendering**:

| Source function | Port as | Change |
|---|---|---|
| `message_handler` (turn entry) | `services/chat.py: handle_turn()` | Remove `cl.Step`; `on_status` publishes a `StatusEvent` to the event bus (task 05) instead of updating a step. |
| `_handle_response` status dispatch | `map_response()` | Return a `ChatMessageResponse` per status instead of sending `cl.Message`. |
| `_handle_needs_info` field mapping (~502–518) | `normalize_followup_questions()` | Keep the id/label/input_type/required/options/default/help mapping; **drop** `AskElementMessage` and the `_depth` recursion — the next POST carries `followup_answers`. |
| `_handle_plan_ready` | plan branch of `map_response()` | Return `{status: plan_ready, plan, auto_approve: settings.auto_approve_steps}`; **drop** `AskActionMessage`. Approval/rejection arrives as the next POST's `plan_approved`/`plan_rejected` (already supported by `A2AClient.send`). |
| `_handle_final_response` | completed branch | Filter `new_artifacts` dropping `metadata.source == "user-upload"` (message_handler.py:672); persist `response.artifacts` into session catalog; pull `follow_up_suggestions` from `message_metadata`; shape artifacts via task 07's metadata builder (no rendering). |
| `_coerce_final_text` | reuse verbatim | report → response_text → message → "N artifact(s) ready." |
| `_handle_backgrounded` | backgrounded branch | Read `task_id` from `message_metadata`; add to session `awaited_task_ids`; return `{status: backgrounded, task_id}`. The **fast-finish snapshot guard** moves to task 05 (events service). |
| `_update_step_statuses` | optional | Only needed if we surface per-step plan status over SSE during execution; can defer. |

## `routers/chat.py`

- `POST /api/chat/messages` — auth required. Body = `ChatMessageRequest`. Resolve
  `conversation_id` + artifacts catalog from session store. Mint a `turn_id`. Call
  `services.chat.handle_turn(...)` with an `on_status` closure that publishes to the session's
  event queue keyed by `turn_id`. Return the mapped `ChatMessageResponse` (with `turn_id`).
- Errors: catch exceptions from `A2AClient.send` and return `{status: error, message}`
  (mirrors message_handler's `"Error communicating with agent"`), not a 500, so the frontend
  renders it inline.

## Acceptance check

- Against a running client-agent: a simple query returns `{status: completed, ...}` with
  `report`/`response_text`.
- A query that triggers follow-up returns `{status: needs_info, followup_questions: [...]}`;
  a second POST with `followup_answers` continues the conversation.
- A plan query returns `{status: plan_ready, plan, auto_approve}`; a POST with
  `plan_approved: true` executes; `plan_rejected: true` clears server state (verify the
  agent's `awaiting_approval` is cleared — see `_handle_plan_ready` reject branch).
- No `cl.*` imports anywhere in the service.
