# Future design: chunked upload for `send_deeplynx_artifact`

## Motivation

`send_deeplynx_artifact` currently uses `AsyncFilesResource.upload()`, which reads the
entire file into memory and sends it in a single multipart POST.  This is fine for
small files but will time out or OOM for large simulation outputs (multi-GB HDF5,
NetCDF, VTK, etc.).

`AsyncFilesResource.upload_chunked()` already exists and streams the file in
configurable-size pieces via `AsyncChunkedUploader`, so the underlying machinery is
in place.

---

## Proposed interface change

Add a `chunked` flag and a `chunk_size` parameter:

```python
async def send_deeplynx_artifact(
    self,
    context: RequestContext,
    event_queue: EventQueue,
    *,
    file_path: Path,
    name: str,
    description: str,
    storage_config: ConnectionConfig,
    mime_type: Optional[str] = None,
    json_type: Optional[str] = None,
    artifact_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    chunked: bool = False,
    chunk_size: int = 5 * 1024 * 1024,   # 5 MB default
) -> ArtifactReference:
```

The upload line becomes:

```python
if chunked:
    file_meta = await client.files.upload_chunked(
        file_path, chunk_size=chunk_size, name=name, description=description
    )
else:
    file_meta = await client.files.upload(file_path, name=name, description=description)
```

Everything after the upload (item creation, URI construction, `send_artifact_reference`)
is identical in both paths.

---

## Auto-threshold option

Rather than requiring callers to set `chunked=True` manually, a follow-on improvement
could transparently switch to chunked upload when the file exceeds a size threshold:

```python
_CHUNKED_THRESHOLD = 50 * 1024 * 1024   # 50 MB

if chunked or file_path.stat().st_size > _CHUNKED_THRESHOLD:
    file_meta = await client.files.upload_chunked(...)
else:
    file_meta = await client.files.upload(...)
```

This would be a safe, backward-compatible change — existing callers get the right
behavior for free.

---

## Progress events during chunked upload

For very large files it would be useful to emit `send_status_update` events as chunks
complete, so the orchestrator and UI can show upload progress.  This requires the
`AsyncChunkedUploader` to expose a progress callback:

```python
async def _on_chunk(n: int, total: int) -> None:
    pct = int(100 * n / total)
    await self.send_status_update(
        context, event_queue,
        message=f"Uploading {name}: {pct}% ({n}/{total} chunks)"
    )

file_meta = await client.files.upload_chunked(
    file_path,
    chunk_size=chunk_size,
    name=name,
    description=description,
    on_chunk=_on_chunk,          # new callback param in AsyncChunkedUploader
)
```

`AsyncChunkedUploader` would need a corresponding `on_chunk` parameter added to its
`upload()` method.

---

## Retry and resume

`AsyncChunkedUploader` retries individual chunks on transient errors (the existing
`max_retries` from `ConnectionConfig` is passed through).  Full resume from a
partially-uploaded file is not currently supported and would require the DeepLynx API
to expose a resumable-upload protocol (e.g. TUS).  This is out of scope for the
initial chunked flag but worth tracking if large-file uploads over unreliable networks
become a requirement.

---

## Implementation checklist (when ready)

- [ ] Add `chunked: bool = False` and `chunk_size: int` params to `send_deeplynx_artifact`
- [ ] Add auto-threshold logic (optional but recommended)
- [ ] Add `on_chunk` progress callback to `AsyncChunkedUploader.upload()`
- [ ] Emit `send_status_update` events from the callback
- [ ] Add `chunked=True` example to `QUICK_START.md`
- [ ] Add integration test with a mock chunked uploader
