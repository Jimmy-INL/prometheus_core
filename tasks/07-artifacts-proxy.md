# 07 — Artifact metadata + content proxy

## Goal

Return artifact **metadata** (with a `render_hint`) in the chat response, and stream artifact
**bytes** through `GET /api/artifacts/{artifact_id}/content` with correct MIME. This replaces
Chainlit's server-side rendering; the React viewers already exist. Decision **D3**.

## Files to create

- `backend/app/services/artifacts.py`
- `backend/app/routers/artifacts.py`

## `services/artifacts.py`

### Metadata builder — `to_artifact_meta(artifact: dict) -> ArtifactMeta`
- Map the raw catalog dict (`artifact_id`, `name`, `mime_type`, `json_type`, `description`,
  `uri`, `tags`, `json_body`, `metadata`, `producer_agent_id`, `created_at`) to `ArtifactMeta`.
- Skip `conversation_message` artifacts (render_artifacts:723 skips `metadata.kind ==
  "conversation_message"` and `name == "conversation_message"`).
- Compute `render_hint` — port the classification. Note there are **two** classifiers in the
  Chainlit code; combine their intent:
  - `_classify_artifact(mime_type)` (message_handler.py:849) → pdf/data/report/file/unknown.
  - The plugin dispatch order (json_type → mime_type → extension) and the richer
    `docs/docs/dev-docs/artifacts.md` table (ifc/exodus/stl/mermaid/reference/visualization).
  - Produce a hint string aligned with the React `classifyElement` kinds
    (`frontend-react/src/lib/chainlit/elements.ts`): `pdf | image | json | suggestions |
    plan_viewer | dynamic_form | ifc | mesh | mermaid | thermal | file | reference | unknown`.
  - Use `json_type` (e.g. `prometheus.thermal_analysis.result.v1` → `thermal`), tags
    (`ifc`/`exodus`/`stl`/`vtk`/`mermaid`/`reference`/`citation`), MIME, then extension.
- Inline `json_body` is passed through so the frontend JSON/thermal viewers render without a
  content fetch.

## `routers/artifacts.py`

- `GET /api/artifacts/{artifact_id}/content` — auth required. Look up the artifact by id in
  the **session's artifact catalog** (populated in task 04's completed branch). Resolve its
  URI to local bytes via `uri_resolver.resolve_to_local_path(uri, cache_dir=..., artifact=...,
  artifact_id=...)` — handles `file://`, `http(s)://`, `deeplynx://`. Stream the file with the
  correct `Content-Type` (from `mime_type` or `mimetypes.guess_type`) and a
  `Content-Disposition` filename. This consolidates `_render_pdf_artifact` /
  `_render_remote_file_artifact` / `_render_file_artifact` / `_render_download_artifact`.
- For inline-only artifacts (json_body/text with no URI), port `_artifact_download_payload`
  (message_handler.py:978): serialize `json_body`→`.json`, text→`.txt`/`.md`, and stream that.
- 404 if the id isn't in the session catalog; 502/failed-resolve → clear error.

## Reference-artifact text (optional)

- `_render_reference_artifact` (message_handler.py:1004) formats citation markdown. This is
  presentational — prefer returning the reference fields as metadata and let the frontend
  format. Only port the formatter if the frontend wants a prebuilt string.

## Acceptance check

- A completed turn with a PDF artifact returns `ArtifactMeta` with `render_hint == "pdf"` and
  a `uri`; `GET /api/artifacts/{id}/content` streams the PDF with `application/pdf`.
- A JSON artifact with inline `json_body` returns it inline (no fetch needed) and
  `render_hint == "json"` (or `thermal` when `json_type` matches).
- A `deeplynx://` artifact resolves and streams (requires DeepLynx creds; otherwise assert
  graceful 502).
- An artifact id not in the session catalog → 404.
