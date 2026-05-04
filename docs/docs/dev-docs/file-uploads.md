# File Upload Workflow

Users can attach files to a query in the Chainlit frontend. This document describes how those files flow through the system to DeepLynx and how they become available to specialist agents.

## High-level flow

```
User attaches file(s) in Chainlit
  → frontend/components/message_handler.py reads files, base64-encodes content
  → ConversationRequest.uploaded_files: [{name, mime_type, size_bytes, content_b64}]
  → client-agent/_execute() calls _handle_uploaded_files() (before routing)
      → infer_file_descriptions() — one LLM call, always returns a string per file
      → upload_files_to_deeplynx() — decode, write temp file, call send_deeplynx_artifact()
      → returns List[str] of newly-created artifact IDs
  → artifact IDs stored in ConversationRequest.newly_uploaded_artifact_ids
  → chat() injects them into previous_context["newly_uploaded_artifact_ids"]
  → planner._build_prompt() prepends "[User-uploaded <type> for this request]" to their descriptions
  → resolve_artifact_inputs() auto-binds (conservative rules below)
```

## Frontend encoding

`frontend/components/message_handler.py` reads each attached file, base64-encodes its content, and includes it in the `uploaded_files` payload sent to the client-agent.  Files handled by a visualization plugin (e.g. IFC viewer) are processed locally and **also** captured for DeepLynx upload.

The payload is capped at `MAX_UPLOAD_BYTES` (20 MB) per file.  Files are passed as:

```json
{
  "name": "reactor_core.exo",
  "mime_type": "application/x-hdf5",
  "size_bytes": 4194304,
  "content_b64": "<base64>"
}
```

## Description inference (`infer_file_descriptions`)

A single LLM call returns a JSON mapping `{filename: description}`.  The prompt instructs the model to use the user's query as context when it's informative, or synthesize a description from the filename and MIME type alone.  The model is explicitly told to **never** return null — a non-empty string is always produced.

If the LLM response cannot be parsed, `_fallback_description()` is used: `"User-uploaded <label>: <filename>"`.

## MIME-to-label mapping (`mime_type_label`)

`file_upload_handler.mime_type_label(mime_type, filename)` produces a human-readable label such as `"Exodus mesh file"` or `"MOOSE input file"`.  It checks:

1. Exact MIME matches (`_EXACT_MIME_LABELS`)
2. File extension matches (`_EXT_LABELS`) — covers nuclear-engineering formats: `.exo`, `.e`, `.i`, `.inp`, `.ifc`, `.h5`, `.nc`, `.vtu`, `.step`, etc.
3. MIME prefix fallbacks (`image/`, `video/`, `audio/`, `text/`, `application/`)

## DeepLynx upload

`upload_files_to_deeplynx` decodes the base64 content, writes a temporary file, then calls `agent.send_deeplynx_artifact()`.  Each uploaded file becomes a conversation-scoped `ArtifactReference` with:

- `tags: ["user-upload"]`
- `metadata: {"original_filename": "<name>", "source": "user-upload"}`
- The inferred description stored in DeepLynx

The temporary file is cleaned up regardless of upload success or failure.

## Ephemeral upload signal in the planner

After upload, the new artifact IDs are stored as `newly_uploaded_artifact_ids` in the conversation context **for the current turn only**.  `merge_artifacts_into_context` drops this key at the start of each subsequent turn so stale data never propagates.

In `planner._build_prompt()`, artifacts whose IDs appear in `newly_uploaded_artifact_ids` have their descriptions prefixed with:

```
[User-uploaded <label> for this request]
```

This prefix helps the planner match the uploaded file to the correct skill parameter even when the user's query uses natural language (e.g. "Convert the attached image").

Example artifact block entry:

```
- reactor_core.exo (id: abc-123) [User-uploaded Exodus mesh file for this request] Reactor core Exodus mesh for neutron flux analysis.
```

## Conservative auto-binding (`resolve_artifact_inputs`)

After the standard UUID/name resolution pass, `resolve_artifact_inputs` performs a conservative auto-binding step:

**Condition**: exactly 1 valid newly-uploaded artifact ID AND exactly 1 still-unfilled `x_artifact_ref` field in the skill's input schema.

**Action**: bind that artifact ID to the field (single-value or list depending on `x_artifact_ref` mode).

**Otherwise**: leave the field empty; the planner is responsible for explicit binding via `set_extracted_params`.

This handles the common single-file upload case without overriding explicit matches or guessing when there is ambiguity.

## Multi-artifact turns

When the user uploads a file **and** references an earlier conversation artifact in the same query (e.g. "Run this input with the mesh you generated earlier"), both artifacts appear in the unified artifact list.  The newly-uploaded file is distinguished only by the ephemeral description prefix.  The planner reads the full context and selects the appropriate artifact IDs for each skill parameter via `set_extracted_params`.

## Error handling

- If DeepLynx is not configured (`ConnectionConfig.from_env()` raises), the upload is skipped with a warning and the artifact IDs list is empty.
- If an individual file upload fails, the warning is logged and the remaining files continue to upload.
- Description inference failures fall back to `"User-uploaded <label>: <filename>"`.
- The router never blocks on upload failures — the request continues without the artifact.
