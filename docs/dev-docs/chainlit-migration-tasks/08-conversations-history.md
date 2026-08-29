# 08 — Conversation history endpoint

## Goal

`GET /api/conversations/recent` returns recent conversation summaries from Redis, replacing
the Chainlit `/history` slash command. Slash-command parsing moves to the frontend.

## Files to create

- `backend/app/routers/conversations.py`

## What to port

- Use `app/conversation_state.py` (lifted in task 03 from the now-removed Chainlit
  `frontend/utils/conversation_state_client.py`; git history).
- Port `_handle_conversation_history` (removed Chainlit `frontend/main.py:107`) as a JSON
  endpoint instead of a markdown
  `cl.Message`: call `ConversationStateClient.get_conversation_history(limit=20)` and return
  the list of `{conversation_id, query, status, material_id, timestamp}` dicts as-is. The
  status inference (`_infer_status`) already lives in the client.
- Degrade gracefully when Redis is unavailable: return `{available: false, conversations: []}`
  (parallels the "History unavailable" message).

## `routers/conversations.py`

- `GET /api/conversations/recent?limit=20` — auth required. Return
  `{available: bool, conversations: [...]}`.

## Acceptance check

- With Redis populated, the endpoint returns recent conversations sorted by timestamp desc.
- With Redis down, returns `{available: false, conversations: []}` and a 200 (not a 500).
