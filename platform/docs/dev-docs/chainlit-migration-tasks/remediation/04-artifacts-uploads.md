# 04 — Artifacts classification + content-proxy + uploads fixes

**Findings:** T-6 `[REG]` (High), A-2 `[REG]`, A-3 `[REG]`, A-4 `[REG]`, A-5/A-6 `[REG]`, A-7 `[REG]`, A-9 `[REG]`.
**Depends on:** 01. **Verify:** `test_artifacts.py` + `test_uploads.py` + new cases green.
**Status:** ✅ Implemented (app/services/artifacts.py, app/routers/artifacts.py, CONTRACT.md; tests in test_artifacts.py + test_contract_matrix.py). T-6 = exodus container MIMEs (`x-hdf5`/`x-netcdf`/`netcdf`) added to the mesh set. A-2 = classifier reordered (specific MIME > tags > extension > generic file MIME), so a specific MIME beats a generic tag but a specific tag beats a generic download MIME. A-3 = per-request temp dir + `BackgroundTask` cleanup (no permanent cache). A-4 = shared `artifact_identity()` mints a stable synthetic id for id-less artifacts, used by both the wire shaper and the content-route lookup. A-5/A-6 = disposition by render_hint (`attachment` for file/unknown) + RFC 5987 filename encoding. A-9 = CSV → `file` (not JSON). **A-7 (graceful failure) and A-8 (frontend gif/webp) left to the frontend** — the backend returns a clean 502 JSON; showing the artifact card when content-fetch fails and the gif/webp image set are frontend concerns (noted in `../frontend/README.md`).

The `uri_resolver`, upload size/MIME/staging, and content-proxy streaming mechanics were
verified faithful — these are the gaps around them.

## T-6 — Uploaded exodus/STL/IFC misclassify (dropped MIME refinement) (High)

Old ran `inspect_upload` and adopted the plugin-refined MIME (`message_handler.py:182`);
new uses only `guess_upload_mime` (`services/uploads.py:104`). Exodus magic-byte/container
MIMEs (`application/x-hdf5`, `application/x-netcdf`, `application/netcdf`) are absent from
every classifier table, so an exodus upload stored as `octet-stream`/`netcdf` later
classifies as `unknown`/`file` (not `mesh`) unless it kept a `.exo`/`.e` name. Fix (choose
the lower-risk): (a) add the container MIMEs to the `mesh` set in `services/artifacts.py`
AND keep extension fallback; and/or (b) port a minimal magic-byte sniff into
`guess_upload_mime` for exodus/HDF5. Prefer (a) as the minimum; add (b) if uploads commonly
arrive without a `.exo/.e/.stl/.ifc` name. Test: an upload with `application/x-netcdf` +
`.e` name → staged/classified as `mesh`.

## A-2 — Tag precedence over MIME can misroute (Medium)

New classifier checks `tags` before `mime_type` (`services/artifacts.py:151`) using generic
tags (`data`,`image`,`pdf`); old never consulted tags. An artifact tagged `data` but
`mime_type application/pdf` → `json` instead of `pdf`. Fix: make `mime_type`/`json_type` the
primary signal and treat tags as a fallback/override only for genuinely ambiguous cases (or
restrict tag routing to specific, unambiguous tags). Test: `{tags:["data"], mime:"application/pdf"}`
→ `pdf`.

## A-3 — Content-proxy cache never evicted (Medium)

`CACHE_DIR` under the system temp (`routers/artifacts.py:37`) keyed by `artifact_id`, no
cleanup — old scoped the resolver to a per-turn `TemporaryDirectory`. Every remote/DeepLynx
fetch leaks a file for the service lifetime and risks stale bytes on id reuse. Fix: bound
the cache (LRU by size/age with eviction) or stream-through without persisting (re-resolve
per request, or a small TTL cache). Keep Range support. Test: cache stays bounded across N
fetches.

## A-4 — Empty `artifact_id` breaks content fetch (Medium)

`to_artifact_meta` defaults `artifact_id=""` when absent (`services/artifacts.py:232`);
`_find_artifact` then matches the first `""`-id entry → `GET /api/artifacts//content` is
ambiguous/unroutable. Fix: skip/mint a stable id for id-less artifacts, or serve id-less
inline artifacts from `json_body`/content without requiring a lookup id; never index on
`""`. Test: two id-less artifacts don't collide; an id-less inline artifact is still
retrievable.

## A-5 / A-6 — Content-Disposition (Low)

`_content_disposition` hardcodes `inline` (`routers/artifacts.py:62`) and doesn't escape the
filename. Fix: use `attachment` for download-class hints (`file`/`unknown`/zip/gzip/
octet-stream), `inline` for viewable types; RFC 5987-encode/escape the filename (guard `"`
and newlines). Test: a zip artifact → `attachment`; a name with a quote is safely encoded.

## A-7 — Graceful resolution failure (Low)

Unresolved/missing path raises hard `502` (`routers/artifacts.py:94`); old fell back to a
text reference. Keep a real error status but ensure the frontend can still show the artifact
reference — return a structured error the viewer can render, or a 404 with a JSON body,
rather than a bare 502. (Coordinate the chosen shape with Bucket A.)

## A-9 — CSV routed to `json` (Low)

`text/csv`/`.csv` → `render_hint="json"` (`services/artifacts.py:74`), which will make the
JSON viewer try to parse CSV. Old effectively fell through to download. Fix: route CSV to
`file` (download) unless/until a CSV/table viewer exists; or add a `table` hint (contract
change — only if wanted). Minimum: don't hand CSV to the JSON viewer.

(A-8 — frontend `isImageFile` omitting gif/webp — is a `frontend/src` classifier
detail; fold into Bucket A's adapter step, not here.)

## Verify

`cd backend && uv run pytest tests/test_artifacts.py tests/test_uploads.py && uv run ruff check && uv run mypy app/`.
