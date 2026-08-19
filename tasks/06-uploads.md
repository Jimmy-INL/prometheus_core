# 06 — File uploads

## Goal

`POST /api/uploads` (multipart) stages a file to DeepLynx via the agent and returns an upload
descriptor the frontend echoes back on the next chat message. Decision **D5**.

## Files to create

- `chat-backend/app/services/uploads.py`
- `chat-backend/app/routers/uploads.py`

## What to port from `frontend/components/message_handler.py`

- **`_guess_upload_mime(filename, element_mime)`** (message_handler.py:62) — verbatim,
  including `CAD_EXTENSION_MIMETYPES` (`.stp`/`.step` → `model/step`) and
  `GENERIC_UPLOAD_MIMETYPES` handling (import the constant from `frontend/plugins/upload_contract.py`
  or re-declare `{"", "application/octet-stream", "binary/octet-stream"}`).
- **Size enforcement** — `MAX_UPLOAD_BYTES` from settings; reject over-limit with a clear 413
  and message (ports `_send_upload_limit_message`).
- **Staging** — `A2AClient.stage_upload(file_path, name, mime_type, conversation_id)` returns
  `{upload_id, name, mime_type, size_bytes}` (ports `_capture_uploaded_file`,
  message_handler.py:84). Requires `upload_id` in the response or it's an error.

## What to DROP (out of scope)

- Server-side plugin `inspect_upload` / `process_upload` / local previews — those produced
  Chainlit elements. Preview is a frontend concern now. We keep only: size limit, MIME guess,
  stage. (Content sniffing for STL/Exodus/IFC lived in the plugins; not ported.)

## `routers/uploads.py`

- `POST /api/uploads` — auth required. Accept `UploadFile` (multipart). Stream to a temp path,
  stat size, enforce limit, guess MIME, call `stage_upload` with the session's
  `conversation_id`. Return `UploadDescriptor` (task 01). Clean up the temp file.
- Support multiple files per request or one-at-a-time — pick one and document; the React
  Chat.tsx uploads per-file today, so **one file per request** is the simplest match.

## Acceptance check

- Upload a small file → `{upload_id, name, mime_type, size_bytes}`; the `upload_id` is
  non-empty.
- Upload a `.step` file → `mime_type == "model/step"`.
- Upload a file over `MAX_UPLOAD_BYTES` → 413 with the limit message.
- Reference the returned `upload_id` in a `POST /api/chat/messages` `upload_ids` and confirm
  the agent receives it (end-to-end in task 10).
