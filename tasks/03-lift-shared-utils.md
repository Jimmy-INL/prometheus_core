# 03 — Lift the Chainlit-free shared utilities

## Goal

Copy the four `frontend/utils/` modules that have **zero Chainlit dependency** into
`chat-backend/app/`, adapting imports and settings references. Leave the originals in place.

## Files to create (copied + adapted)

| New file | Source | Changes needed |
|---|---|---|
| `app/a2a_client.py` | `frontend/utils/a2a_client.py` | Swap `from utils.settings import settings` → `from app.config import settings`. Keep the `prometheus_api.contract` + `prometheus_api.a2a_stream` imports verbatim. No logic change. |
| `app/task_events.py` | `frontend/utils/task_events.py` | None functional — pure Redis pub/sub. Keep `TERMINAL_STATES`, `subscribe`, `fetch_result`, `node_snapshot`, `node_state`, `is_terminal`, channel helpers. |
| `app/uri_resolver.py` | `frontend/utils/uri_resolver.py` | None functional — keep `resolve_to_local_path` + `_resolve_deeplynx` + `_parse_item_id`. Depends on `prometheus_api.storage_client` (present via base image dep). |
| `app/conversation_state.py` | `frontend/utils/conversation_state_client.py` | None functional — keep `ConversationStateClient` (sync redis, read-only history). |

## Details

- `A2AClient` is the workhorse: `send(query, conversation_id, artifacts, followup_answers,
  plan_approved, plan_rejected, workflow_id, uploaded_files, on_status)` and
  `stage_upload(file_path, name, mime_type, conversation_id)`. It already supports the entire
  inverted-loop field set — **no new fields needed**.
- `task_events` channel contract (do not change): events on `tasks:events:{conversation_id}`,
  results at `tasks:result:{cid}:{tid}`, node snapshots at `tasks:node:{cid}:{tid}`.
- Confirm `prometheus_api.a2a_stream.consume_stream_response(response, status_callback=...)`
  is importable in this service (it is the streaming parser `A2AClient` delegates to).

## Acceptance check

- All four modules import under the new package path; `uv run mypy app/` passes.
- A unit test constructs `A2AClient(agent_url, secret)` and asserts the JSON-RPC envelope
  built by `send()` matches the expected shape (can test `_extract_from_status` with a
  canned A2A payload without a live agent).
- `task_events.is_terminal("completed")` is `True`; `events_channel("x")` == `tasks:events:x`.

## Notes

- Do **not** copy `frontend/utils/settings.py` — task 00 already created `app/config.py`.
- Do **not** copy `frontend/utils/logger.py` unless a shared logging setup is wanted; prefer
  stdlib logging config in `app/main.py`.
