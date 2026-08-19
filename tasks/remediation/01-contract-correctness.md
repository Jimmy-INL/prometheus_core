# 01 — Contract correctness (freeze a *correct* contract before the cutover)

**Findings:** DOC-1 `[DOC]`, T-3/A2 `[REG]`, CON-1 `[REG]`, A-1 `[REG]`.
**Depends on:** 00. **Verify:** `test_contract_matrix.py` + new cases green; `CONTRACT.md` and `app/contract.py` agree.
**Status:** ✅ Implemented (chat-backend/app/contract.py, chat-backend/app/services/artifacts.py, chat-backend/CONTRACT.md; tests extended in test_artifacts.py + test_contract_matrix.py). Canonical enum = current + `report`; `svg`→`image`, `json` (not `data`) kept; `Citation` is a typed sub-model. See the Progress log in `README.md`. **Frontend impact:** the adapter must render `report` as markdown and read `ArtifactMeta.citation` for `reference` cards.

`../frontend/README.md` codes against a *frozen* contract. These four items are places
where the frozen contract is wrong or ambiguous; fixing them now avoids re-work in the
cutover. Any shape change updates `chat-backend/CONTRACT.md` + `app/contract.py` +
contract tests together.

## DOC-1 — Reconcile the `render_hint` enum (single source of truth)

`app/contract.py` `RenderHint` = `pdf, image, json, ifc, mesh, mermaid, thermal, reference,
file, unknown`. `CONTRACT.md` table = `mesh, ifc, mermaid, image, svg, pdf, data, report,
reference, file, unknown`. They disagree on `json`↔`data`, `svg`, `report`, `thermal`.

Decide the canonical set and make both match. Recommended canonical (superset that keeps
the classifier expressive and matches the React `ElementKind`/`VIEWER_REGISTRY` the adapter
will target): `pdf, image, svg, mesh, ifc, mermaid, thermal, json, report, reference, file,
unknown`. This resolves A-1 (add `report`) and keeps `svg` distinct (the frontend has an
SVGViewer). Update `classify_render_hint` in `services/artifacts.py` to emit the canonical
values, update `CONTRACT.md`, and add the `render_hint` list to a contract test so the two
can't drift again.

## T-3 / A2 — Loosen `FormField.input_type` off the strict `Literal`

`FormField.input_type: FieldInputType` (a 9-value `Literal`) is fed the raw agent `type`
(`contract.py:132`); a nonstandard/empty value raises `ValidationError`, caught by the
router's blanket `except` and mislabeled as an agent-comms **error** — the whole form is
lost. Old code passed the type through and the JSX defaulted to `text`.

Fix in `normalize_followup_questions` (`app/contract.py`): map unknown/empty types to
`"text"` (keep the known set as-is) so a legitimate `needs_info` always renders. Keep the
field type as the `Literal` on the wire, but coerce during normalization — do **not** feed
raw values straight into the model. Add a test: an agent field with `type:"radio"` and one
with `type:""` both yield `input_type:"text"` and a valid `needs_info` response (not
`error`).

## CON-1 — Carry reference/citation metadata on the wire

`ArtifactMeta` has no nested `metadata`, so `to_artifact_meta` (`services/artifacts.py:218`)
drops `metadata.source/section/page` — the exact fields the old citation renderer used
(`message_handler.py:1004-1018`). The `render_hint=="reference"` doc says "frontend formats
from metadata," but nothing is on the wire.

Fix: add an optional structured field to `ArtifactMeta` carrying at least
`source`, `section`, `page` (e.g. `citation: Optional[Citation]` or a passthrough
`metadata: Optional[dict]` scoped to citation keys — prefer a typed sub-model for the
frozen contract). Populate it in `to_artifact_meta` from the raw artifact's `metadata`.
Update `CONTRACT.md`'s artifact example + the `reference` row. The `reference` **viewer**
itself is Bucket A (frontend); this step just stops the data loss.

## A-1 — Markdown/plain reports: don't silently become downloads

`text/markdown` / `text/plain` currently map to `render_hint="file"`
(`services/artifacts.py:76`), so inline reports the old app rendered as markdown
(`message_handler.py:810`) would download. With `report` added to the enum (DOC-1), route
`text/markdown` (and `.md`) → `report`; leave `text/plain`/`.txt` a judgment call
(recommend `report` for `.md`, `file` for arbitrary `.txt` unless tagged). Add a classifier
test.

## Verify

`cd chat-backend && uv run pytest tests/test_contract_matrix.py tests/test_artifacts.py &&
uv run ruff check && uv run mypy app/`. Confirm `CONTRACT.md` render_hint table == the
enum. **Pause for review here** (contract changes gate the frontend build).
