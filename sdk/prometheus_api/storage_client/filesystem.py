"""DeepLynx-backed fsspec filesystem with S3-like bucket/key semantics.

This module implements an ``AbstractFileSystem`` for the ``deeplynx://`` protocol.
It uses DeepLynx's existing file upload/download endpoints while emulating object
store behavior expected by fsspec consumers.

Implementation overview:
- Paths are interpreted as ``deeplynx://<bucket>/<key>``.
- Buckets and directories are virtual (derived from key prefixes).
- Object identity is tracked in a single DeepLynx record ("index record") that maps
  each ``bucket/key`` to a DeepLynx file record ID.
- Reads resolve through the index and then download by record ID.
- Writes upload first, then atomically repoint the index entry to the new record ID.

Because DeepLynx is not a native object store with first-class key listing, the
index record is authoritative for all namespace operations.
"""

import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fsspec import AbstractFileSystem
from fsspec.registry import register_implementation
from fsspec.utils import stringify_path

from .client import StorageClient
from .connection import ConnectionConfig
from .models.file import FileMetadata
from .models.item import ItemCreate, ItemUpdate


@dataclass
class _IndexEntry:
    """Normalized metadata for one object entry in the index record.

    The key for this entry lives in ``_IndexState.entries`` as ``"bucket/key"``.
    """

    record_id: int
    size: Optional[int] = None
    file_type: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class _IndexState:
    """In-memory snapshot of the index record.

    Attributes:
        record_id: DeepLynx record ID of the index metadata record.
        buckets: Known virtual bucket names.
        entries: Object map of ``"bucket/key"`` to ``_IndexEntry``.
        directories: Optional persisted directory placeholders per bucket.
    """

    record_id: int
    buckets: Set[str]
    entries: Dict[str, _IndexEntry]
    directories: Dict[str, Set[str]]


class _DeepLynxWriteFile(io.BytesIO):
    """In-memory write buffer that commits object bytes on close.

    ``fsspec`` expects file-like objects for write modes. This class captures all
    writes in memory and performs a single commit operation when closed, ensuring the
    index update and optional old-record cleanup happen in one controlled place.
    """

    def __init__(self, fs: "DeeplynxFileSystem", path: str, mode: str, initial: bytes = b""):
        super().__init__(initial)
        self._fs = fs
        self._path = path
        self._mode = mode
        self._committed = False

    def close(self) -> None:
        """Commit buffered bytes exactly once, then close the buffer."""
        if not self.closed and not self._committed:
            payload = self.getvalue()
            self._fs._commit_bytes(self._path, payload, self._mode)
            self._committed = True
        super().close()


class DeeplynxFileSystem(AbstractFileSystem):
    """fsspec filesystem backed by DeepLynx file APIs.

    This class provides an object-store style interface over DeepLynx by maintaining
    an index record that maps virtual object keys to concrete DeepLynx file record IDs.
    The protocol remains ``deeplynx://``, while behavior intentionally mirrors common
    S3 patterns where possible.

    Path model:
    - ``deeplynx://``: filesystem root listing virtual buckets
    - ``deeplynx://<bucket>``: virtual bucket directory
    - ``deeplynx://<bucket>/<prefix>/.../<name>``: object key

    Core behavior:
    - ``ls/info/exists/isdir/isfile`` are derived from the index record.
    - ``open(..., "rb")`` downloads object bytes by record ID from DeepLynx.
    - ``open(..., "wb"|"xb"|"ab")`` writes via upload, then updates index mapping.
    - Overwrite is "upload then swap index pointer", with best-effort deletion of
      the replaced record when enabled.

    Index record schema (stored in item properties):
    - ``_deeplynx_fsspec_index``: marker bool
    - ``version``: schema version
    - ``buckets``: list of bucket names
    - ``entries``: mapping of ``"bucket/key"`` to record metadata
    - ``directories``: optional explicit directory placeholders

    Lifecycle model:
    - If ``client`` is supplied, it is treated as externally managed.
    - If ``config`` is supplied, an internal client is created lazily.
    - If both are ``None``, configuration defaults to ``ConnectionConfig.from_env()``.
    - If both are supplied, initialization fails to prevent ambiguous ownership.

    Usage examples:
        >>> from fsspec import filesystem
        >>> fs = filesystem("deeplynx")  # uses ConnectionConfig.from_env()
        >>> fs.pipe_file("deeplynx://models/run-1/results.bin", b"payload")
        >>> fs.cat_file("deeplynx://models/run-1/results.bin")
        b'payload'
        >>> fs.ls("deeplynx://models", detail=False)
        ['models/run-1']

        >>> from prometheus_api.storage_client import ConnectionConfig
        >>> cfg = ConnectionConfig.from_env()
        >>> fs = filesystem("deeplynx", config=cfg)
        >>> with fs.open("deeplynx://artifacts/a.txt", "wb") as f:
        ...     _ = f.write(b"hello")
        >>> fs.put("local/input.csv", "deeplynx://staging/entity-a/input.csv")
        >>> fs.get("deeplynx://staging/entity-a/input.csv", "local/staged-input.csv")

    Notes and limitations:
    - Namespace operations are only as complete as the index record.
    - Concurrent writers are last-write-wins (no optimistic concurrency lock).
    - Append mode performs read-then-rewrite, not server-side append.
    """

    protocol = "deeplynx"
    root_marker = ""

    def __init__(
        self,
        config: Optional[ConnectionConfig] = None,
        client: Optional[StorageClient] = None,
        *,
        index_name: str = "__deeplynx_fsspec_index__",
        index_original_id: str = "deeplynx-fsspec-index",
        index_scan_page_size: int = 100,
        auto_mkdir: bool = True,
        delete_replaced_records: bool = True,
        **kwargs,
    ):
        """Initialize the DeepLynx filesystem adapter.

        Args:
            config: Optional connection settings used to lazily create and own a
                ``StorageClient``.
            client: Optional pre-built ``StorageClient`` managed by the caller.
            index_name: Human-readable name for the DeepLynx index record.
            index_original_id: Stable record identity used to discover the index.
            index_scan_page_size: Page size when scanning project records to locate
                the index record.
            auto_mkdir: If ``True``, parent prefixes are auto-created during writes.
            delete_replaced_records: If ``True``, overwritten object records are
                best-effort deleted after index pointer swap.
            **kwargs: Additional ``fsspec.AbstractFileSystem`` arguments.

        Raises:
            ValueError: If both ``config`` and ``client`` are provided.
        """
        if config is not None and client is not None:
            raise ValueError("Provide either config or client, not both")

        if client is None and config is None:
            config = ConnectionConfig.from_env()

        super().__init__(**kwargs)

        self._config = config
        self._client = client
        self._owns_client = client is None
        self._owned_client: Optional[StorageClient] = None

        self._index_name = index_name
        self._index_original_id = index_original_id
        self._index_scan_page_size = max(1, index_scan_page_size)
        self._auto_mkdir = auto_mkdir
        self._delete_replaced_records = delete_replaced_records

        self._index_state: Optional[_IndexState] = None

    @classmethod
    def _strip_protocol(cls, path: Any) -> str:
        """Normalize a path to filesystem-relative ``bucket/key`` form."""
        if isinstance(path, list):
            return [cls._strip_protocol(p) for p in path]

        path = stringify_path(path)
        path = path.removeprefix("deeplynx://")
        if "://" in path or "::" in path:
            return path.rstrip("/")
        return path.lstrip("/").rstrip("/")

    def close(self) -> None:
        """Close an internally owned client, if one was created."""
        if self._owns_client and self._owned_client is not None:
            self._owned_client.__exit__(None, None, None)
            self._owned_client = None
            self._client = None

    def invalidate_cache(self, path: Optional[str] = None) -> None:
        """Invalidate fsspec caches and the in-memory index snapshot."""
        super().invalidate_cache(path)
        self._index_state = None

    def ls(self, path: str, detail: bool = True, **kwargs):
        """List buckets, directories, or files at ``path``.

        The listing is driven by index state, not by direct DeepLynx key scans.
        """
        normalized = self._strip_protocol(path)
        index = self._load_index()

        if normalized == "":
            # Root lists known virtual buckets.
            out = [
                {"name": bucket, "size": 0, "type": "directory"} for bucket in sorted(index.buckets)
            ]
            return out if detail else [item["name"] for item in out]

        bucket, key = self._split_path(normalized)

        if key and self._file_entry(index, bucket, key):
            info = self._file_info(bucket, key, self._file_entry(index, bucket, key))
            return [info] if detail else [info["name"]]

        if not self._directory_exists(index, bucket, key):
            raise FileNotFoundError(path)

        out = self._list_directory(index, bucket, key)
        return out if detail else [item["name"] for item in out]

    def info(self, path: str, **kwargs) -> Dict[str, Any]:
        """Return metadata for a single path (file or virtual directory)."""
        normalized = self._strip_protocol(path)
        if normalized == "":
            return {"name": "", "size": 0, "type": "directory"}

        index = self._load_index()
        bucket, key = self._split_path(normalized)
        entry = self._file_entry(index, bucket, key)
        if entry:
            return self._file_info(bucket, key, entry)

        if self._directory_exists(index, bucket, key):
            return {"name": normalized, "size": 0, "type": "directory"}

        raise FileNotFoundError(path)

    def exists(self, path: str, **kwargs) -> bool:
        """Return ``True`` when a file or directory-like prefix exists."""
        try:
            self.info(path, **kwargs)
            return True
        except Exception:
            return False

    def isfile(self, path: str) -> bool:
        """Return ``True`` when ``path`` resolves to an indexed object."""
        normalized = self._strip_protocol(path)
        if normalized == "":
            return False
        index = self._load_index()
        bucket, key = self._split_path(normalized)
        return self._file_entry(index, bucket, key) is not None

    def isdir(self, path: str) -> bool:
        """Return ``True`` for root, buckets, or virtual prefix directories."""
        normalized = self._strip_protocol(path)
        if normalized == "":
            return True
        index = self._load_index()
        bucket, key = self._split_path(normalized)
        if self._file_entry(index, bucket, key):
            return False
        return self._directory_exists(index, bucket, key)

    def mkdir(self, path: str, create_parents: bool = True, **kwargs) -> None:
        """Create a virtual bucket or directory placeholder in index metadata."""
        normalized = self._strip_protocol(path)
        if normalized == "":
            return

        index = self._load_index()
        bucket, prefix = self._split_path(normalized)
        if self._file_entry(index, bucket, prefix):
            raise FileExistsError(path)
        if self._directory_exists(index, bucket, prefix):
            raise FileExistsError(path)

        self._ensure_directory(index, bucket, prefix, create_parents=create_parents)
        self._save_index(index)

    def makedirs(self, path: str, exist_ok: bool = False):
        """Recursively create virtual directories, matching ``os.makedirs`` behavior."""
        try:
            self.mkdir(path, create_parents=True)
        except FileExistsError:
            if not exist_ok:
                raise

    def rm(self, path, recursive: bool = False, maxdepth: Optional[int] = None):
        """Remove one or more files/directories.

        Directories require ``recursive=True`` because they are expanded using index
        state rather than backend-native directory semantics.
        """
        paths = path if isinstance(path, list) else [path]
        for p in paths:
            normalized = self._strip_protocol(p)
            if normalized == "":
                if recursive:
                    # Recursive root delete means "delete all indexed objects".
                    self._rm_root()
                    continue
                raise IsADirectoryError(p)

            if self.isfile(normalized):
                self.rm_file(normalized)
                continue

            if not self.isdir(normalized):
                raise FileNotFoundError(p)

            if not recursive:
                raise IsADirectoryError(p)

            self._rm_directory(normalized, maxdepth=maxdepth)

    def rm_file(self, path: str):
        """Delete one file object and remove its index entry."""
        normalized = self._strip_protocol(path)
        bucket, key = self._split_path(normalized)
        if key == "":
            raise IsADirectoryError(path)

        index = self._load_index()
        entry_key = self._entry_key(bucket, key)
        entry = index.entries.get(entry_key)
        if not entry:
            raise FileNotFoundError(path)

        self._client_or_raise().files.delete(entry.record_id)
        del index.entries[entry_key]
        self._save_index(index)

    def cat_file(self, path: str, start: Optional[int] = None, end: Optional[int] = None, **kwargs):
        """Read bytes for an object, optionally slicing using start/end offsets."""
        normalized = self._strip_protocol(path)
        bucket, key = self._split_path(normalized)
        entry = self._file_entry(self._load_index(), bucket, key)
        if not entry:
            raise FileNotFoundError(path)

        raw = self._download_record(entry.record_id)
        length = len(raw)

        if start is None:
            start_idx = 0
        elif start >= 0:
            start_idx = start
        else:
            start_idx = max(0, length + start)

        if end is None:
            end_idx = length
        elif end >= 0:
            end_idx = end
        else:
            end_idx = length + end

        return raw[start_idx:end_idx]

    def pipe_file(self, path: str, value: bytes, mode: str = "overwrite", **kwargs):
        """Write bytes directly to an object key."""
        if mode == "create" and self.exists(path):
            raise FileExistsError(path)
        if isinstance(value, str):
            value = value.encode()
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("pipe_file expects bytes-like content")
        self._commit_bytes(path, bytes(value), "xb" if mode == "create" else "wb")

    def touch(self, path: str, truncate: bool = True, **kwargs):
        """Create/truncate an empty object.

        Timestamp-only updates are not supported by this backend.
        """
        normalized = self._strip_protocol(path)
        if truncate or not self.exists(normalized):
            self.pipe_file(normalized, b"", mode="overwrite")
        else:
            raise NotImplementedError("Timestamp updates are not supported")

    def _open(
        self,
        path: str,
        mode: str = "rb",
        block_size=None,
        autocommit: bool = True,
        cache_options=None,
        **kwargs,
    ):
        """Open a file-like handle for supported binary modes.

        Supported modes are ``rb``, ``wb``, ``xb``, and ``ab``.
        """
        normalized = self._strip_protocol(path)
        if normalized == "":
            raise IsADirectoryError(path)

        if mode == "rb":
            return io.BytesIO(self.cat_file(normalized))
        if mode == "wb":
            return _DeepLynxWriteFile(self, normalized, mode)
        if mode == "xb":
            if self.exists(normalized):
                raise FileExistsError(path)
            return _DeepLynxWriteFile(self, normalized, mode)
        if mode == "ab":
            # Append is implemented as "read current bytes then rewrite on close".
            initial = self.cat_file(normalized) if self.exists(normalized) else b""
            writer = _DeepLynxWriteFile(self, normalized, mode, initial=initial)
            writer.seek(0, io.SEEK_END)
            return writer
        raise ValueError(f"Unsupported file mode: {mode!r}")

    def _commit_bytes(self, path: str, data: bytes, mode: str) -> None:
        """Upload object bytes and persist index updates.

        For overwrites, this method performs:
        1. Upload new bytes to DeepLynx (new record ID)
        2. Update index entry to point at new record
        3. Optionally best-effort delete old record
        """
        normalized = self._strip_protocol(path)
        bucket, key = self._split_path(normalized)
        if key == "":
            raise IsADirectoryError(path)

        index = self._load_index()
        existing = self._file_entry(index, bucket, key)
        if mode == "xb" and existing:
            raise FileExistsError(path)

        self._ensure_parent_for_write(index, bucket, key)
        # Upload first so failures do not corrupt the previous index pointer.
        uploaded = self._upload_bytes(bucket, key, data)
        entry_key = self._entry_key(bucket, key)
        index.entries[entry_key] = _IndexEntry(
            record_id=uploaded.id,
            size=uploaded.size,
            file_type=uploaded.file_type,
            updated_at=uploaded.updated_at.isoformat() if uploaded.updated_at else None,
        )
        self._save_index(index)

        if existing and self._delete_replaced_records:
            try:
                self._client_or_raise().files.delete(existing.record_id)
            except Exception:
                # Best effort cleanup: leave orphaned historical records if delete fails.
                pass

    def _upload_bytes(self, bucket: str, key: str, data: bytes) -> FileMetadata:
        """Upload raw bytes through existing file upload API.

        The current storage client upload API accepts filesystem paths, so this
        adapter writes bytes to a temporary file and uploads from that path.
        """
        _, suffix = os.path.splitext(key)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin")
        try:
            tmp.write(data)
            tmp.flush()
            tmp.close()
            filename = key.rsplit("/", 1)[-1]
            return self._client_or_raise().files.upload(
                Path(tmp.name),
                name=filename,
                description=f"deeplynx://{bucket}/{key}",
            )
        finally:
            try:
                os.unlink(tmp.name)
            except FileNotFoundError:
                pass

    def _download_record(self, record_id: int) -> bytes:
        """Download bytes for a concrete DeepLynx file record ID."""
        response = self._client_or_raise()._request(
            "GET",
            f"{self._records_base_path()}/files/{record_id}",
        )
        return response.content

    def _records_base_path(self) -> str:
        """Return API base path scoped to configured organization/project."""
        client = self._client_or_raise()
        return (
            f"/organizations/{client.config.organization_id}"
            f"/projects/{client.config.project_id}"
        )

    def _client_or_raise(self) -> StorageClient:
        """Return an active client, lazily creating one when owned by this FS."""
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            if self._config is None:
                raise ValueError("ConnectionConfig is required when no client is provided")
            # Lazily enter context so construction is cheap and env errors can surface
            # only when backend interaction is first needed.
            self._owned_client = StorageClient(self._config)
            self._client = self._owned_client.__enter__()
        return self._client

    def _split_path(self, path: str) -> Tuple[str, str]:
        """Split normalized path into ``(bucket, key)``."""
        normalized = self._strip_protocol(path)
        if normalized == "":
            raise ValueError("Path must include a bucket")
        parts = normalized.split("/", 1)
        bucket = parts[0].strip()
        if not bucket:
            raise ValueError(f"Invalid path {path!r}: missing bucket")
        key = parts[1] if len(parts) > 1 else ""
        key = key.strip("/")
        return bucket, key

    def _entry_key(self, bucket: str, key: str) -> str:
        """Create canonical index key format."""
        return f"{bucket}/{key}"

    def _file_entry(self, index: _IndexState, bucket: str, key: str) -> Optional[_IndexEntry]:
        """Resolve a file entry from the index if this path is a file key."""
        if key == "":
            return None
        return index.entries.get(self._entry_key(bucket, key))

    def _file_info(self, bucket: str, key: str, entry: _IndexEntry) -> Dict[str, Any]:
        """Build fsspec-compatible file detail payload."""
        return {
            "name": self._entry_key(bucket, key),
            "size": entry.size,
            "type": "file",
            "record_id": entry.record_id,
            "file_type": entry.file_type,
            "updated_at": entry.updated_at,
        }

    def _list_directory(self, index: _IndexState, bucket: str, prefix: str) -> List[Dict[str, Any]]:
        """List direct children under a bucket/prefix path."""
        files: Dict[str, Dict[str, Any]] = {}
        directories: Set[str] = set()
        prefix_base = f"{prefix}/" if prefix else ""

        for full_key, entry in index.entries.items():
            entry_bucket, object_key = full_key.split("/", 1)
            if entry_bucket != bucket:
                continue
            if prefix:
                if object_key == prefix:
                    continue
                if not object_key.startswith(prefix_base):
                    continue
                tail = object_key[len(prefix_base) :]
            else:
                tail = object_key

            if "/" in tail:
                # Deeper object implies an intermediate virtual directory.
                directories.add(tail.split("/", 1)[0])
            elif tail:
                files[full_key] = self._file_info(bucket, object_key, entry)

        for directory in index.directories.get(bucket, set()):
            if prefix:
                if directory == prefix:
                    continue
                if not directory.startswith(prefix_base):
                    continue
                tail = directory[len(prefix_base) :]
            else:
                tail = directory
            if not tail:
                continue
            directories.add(tail.split("/", 1)[0])

        out = list(files.values())
        for child in directories:
            name = f"{bucket}/{prefix_base}{child}" if prefix_base else f"{bucket}/{child}"
            out.append({"name": name, "size": 0, "type": "directory"})
        out.sort(key=lambda item: item["name"])
        return out

    def _directory_exists(self, index: _IndexState, bucket: str, prefix: str) -> bool:
        """Return whether a directory-like path should be considered present."""
        if bucket not in index.buckets:
            return False
        if prefix == "":
            return True

        prefix_base = f"{prefix}/"
        for full_key in index.entries:
            entry_bucket, object_key = full_key.split("/", 1)
            if entry_bucket == bucket and object_key.startswith(prefix_base):
                return True

        bucket_dirs = index.directories.get(bucket, set())
        if prefix in bucket_dirs:
            return True
        for directory in bucket_dirs:
            if directory.startswith(prefix_base):
                return True
        return False

    def _ensure_directory(
        self,
        index: _IndexState,
        bucket: str,
        prefix: str,
        *,
        create_parents: bool,
    ) -> None:
        """Create bucket/prefix placeholders in the index."""
        if not create_parents and prefix:
            parent = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
            if parent and not self._directory_exists(index, bucket, parent):
                raise FileNotFoundError(parent)
            if not parent and bucket not in index.buckets:
                raise FileNotFoundError(bucket)

        index.buckets.add(bucket)
        dirs = index.directories.setdefault(bucket, set())
        if prefix == "":
            return
        if create_parents:
            parts = prefix.split("/")
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        else:
            dirs.add(prefix)

    def _ensure_parent_for_write(self, index: _IndexState, bucket: str, key: str) -> None:
        """Ensure parent namespace exists or auto-create it for writes."""
        parent = key.rsplit("/", 1)[0] if "/" in key else ""
        if self._auto_mkdir:
            self._ensure_directory(index, bucket, parent, create_parents=True)
            return
        if bucket not in index.buckets:
            raise FileNotFoundError(bucket)
        if parent and not self._directory_exists(index, bucket, parent):
            raise FileNotFoundError(parent)

    def _rm_root(self) -> None:
        """Delete all indexed objects and clear virtual namespace metadata."""
        index = self._load_index()
        record_ids = [entry.record_id for entry in index.entries.values()]
        for record_id in record_ids:
            self._client_or_raise().files.delete(record_id)
        index.entries.clear()
        index.directories = {}
        index.buckets = set()
        self._save_index(index)

    def _rm_directory(self, path: str, maxdepth: Optional[int] = None) -> None:
        """Recursively delete objects under a directory-like path."""
        index = self._load_index()
        bucket, prefix = self._split_path(path)
        if not self._directory_exists(index, bucket, prefix):
            raise FileNotFoundError(path)

        prefix_base = f"{prefix}/" if prefix else ""
        entry_keys_to_delete: List[str] = []
        for full_key in list(index.entries):
            entry_bucket, object_key = full_key.split("/", 1)
            if entry_bucket != bucket:
                continue
            if prefix and not object_key.startswith(prefix_base):
                continue
            depth = 1 if not prefix else object_key[len(prefix_base) :].count("/") + 1
            if maxdepth is not None and depth > maxdepth:
                continue
            entry_keys_to_delete.append(full_key)

        for full_key in entry_keys_to_delete:
            entry = index.entries[full_key]
            self._client_or_raise().files.delete(entry.record_id)
            del index.entries[full_key]

        if prefix == "":
            index.directories.pop(bucket, None)
            index.buckets.discard(bucket)
        else:
            dirs = index.directories.get(bucket, set())
            dirs_to_remove = {d for d in dirs if d == prefix or d.startswith(prefix_base)}
            dirs.difference_update(dirs_to_remove)
            if not dirs and bucket in index.directories:
                index.directories[bucket] = dirs

        self._save_index(index)

    def _load_index(self) -> _IndexState:
        """Load index metadata from cache or DeepLynx record listing."""
        if self._index_state is not None:
            return self._index_state

        index_record_id: Optional[int] = None
        index_props: Optional[Dict[str, Any]] = None

        for record in self._iter_records():
            original_id = record.get("originalId") or record.get("original_id")
            properties = self._coerce_properties(record.get("properties"))
            is_marker = bool(properties.get("_deeplynx_fsspec_index") is True)
            if original_id == self._index_original_id and is_marker:
                # Exact match is authoritative.
                index_record_id = int(record["id"])
                index_props = properties
                break
            if index_record_id is None and (original_id == self._index_original_id or is_marker):
                # Keep first partial match as fallback if exact marker+id is absent.
                index_record_id = int(record["id"])
                index_props = properties

        if index_record_id is None:
            # Bootstrap a new index record on first filesystem use.
            index_props = self._default_index_properties()
            item = self._client_or_raise().items.create(
                ItemCreate(
                    name=self._index_name,
                    description="DeepLynx fsspec index record",
                    original_id=self._index_original_id,
                    properties=index_props,
                )
            )
            index_record_id = item.id

        self._index_state = self._normalize_index(index_record_id, index_props or {})
        return self._index_state

    def _iter_records(self) -> Iterable[Dict[str, Any]]:
        """Yield project records page-by-page for index discovery."""
        page = 1
        while True:
            response = self._client_or_raise()._request(
                "GET",
                f"{self._records_base_path()}/records",
                params={"page": page, "limit": self._index_scan_page_size},
            )
            payload = response.json()
            if isinstance(payload, list):
                records = payload
            else:
                records = payload.get("records", [])

            if not records:
                break

            for record in records:
                if isinstance(record, dict):
                    yield record

            if len(records) < self._index_scan_page_size:
                break
            page += 1

    def _default_index_properties(self) -> Dict[str, Any]:
        """Return default persisted index property structure."""
        return {
            "_deeplynx_fsspec_index": True,
            "version": 1,
            "buckets": [],
            "entries": {},
            "directories": {},
        }

    def _coerce_properties(self, properties: Any) -> Dict[str, Any]:
        """Parse DeepLynx ``properties`` payload into a dict safely."""
        if isinstance(properties, dict):
            return dict(properties)
        if isinstance(properties, str):
            try:
                parsed = json.loads(properties)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _normalize_index(self, record_id: int, props: Dict[str, Any]) -> _IndexState:
        """Normalize persisted index JSON into strongly-typed internal state."""
        buckets = {b for b in props.get("buckets", []) if isinstance(b, str) and b}

        entries: Dict[str, _IndexEntry] = {}
        raw_entries = props.get("entries", {})
        if isinstance(raw_entries, dict):
            for full_key, raw_entry in raw_entries.items():
                if not isinstance(full_key, str) or "/" not in full_key:
                    continue
                if not isinstance(raw_entry, dict):
                    continue
                raw_record_id = raw_entry.get("record_id", raw_entry.get("recordId"))
                if raw_record_id is None:
                    continue
                try:
                    mapped_record_id = int(raw_record_id)
                except (TypeError, ValueError):
                    continue

                raw_size = raw_entry.get("size")
                size = None
                if raw_size is not None:
                    try:
                        size = int(raw_size)
                    except (TypeError, ValueError):
                        size = None

                entries[full_key] = _IndexEntry(
                    record_id=mapped_record_id,
                    size=size,
                    file_type=raw_entry.get("file_type", raw_entry.get("fileType")),
                    updated_at=raw_entry.get("updated_at", raw_entry.get("updatedAt")),
                )
                buckets.add(full_key.split("/", 1)[0])

        directories: Dict[str, Set[str]] = {}
        raw_dirs = props.get("directories", {})
        if isinstance(raw_dirs, dict):
            for bucket, raw_prefixes in raw_dirs.items():
                if not isinstance(bucket, str) or not bucket:
                    continue
                if not isinstance(raw_prefixes, list):
                    continue
                prefixes = {
                    prefix.strip("/")
                    for prefix in raw_prefixes
                    if isinstance(prefix, str) and prefix.strip("/") != ""
                }
                directories[bucket] = prefixes
                buckets.add(bucket)

        for full_key in entries:
            bucket, key = full_key.split("/", 1)
            if "/" in key:
                dirs = directories.setdefault(bucket, set())
                parts = key.split("/")[:-1]
                for i in range(1, len(parts) + 1):
                    dirs.add("/".join(parts[:i]))

        return _IndexState(
            record_id=record_id, buckets=buckets, entries=entries, directories=directories
        )

    def _save_index(self, index: _IndexState) -> None:
        """Persist index state to DeepLynx and refresh local cache references."""
        props = self._serialize_index(index)
        self._client_or_raise().items.update(
            index.record_id,
            ItemUpdate(properties=props),
        )
        # Keep cache coherent for callers in this process while still invalidating
        # fsspec-level listing caches.
        self._index_state = index
        self.invalidate_cache()
        self._index_state = index

    def _serialize_index(self, index: _IndexState) -> Dict[str, Any]:
        """Serialize internal index state into JSON-safe record properties."""
        entries: Dict[str, Dict[str, Any]] = {}
        for full_key in sorted(index.entries):
            item = index.entries[full_key]
            entries[full_key] = {
                "record_id": item.record_id,
                "size": item.size,
                "file_type": item.file_type,
                "updated_at": item.updated_at,
            }

        directories: Dict[str, List[str]] = {}
        for bucket, prefixes in sorted(index.directories.items()):
            if not prefixes:
                continue
            directories[bucket] = sorted(prefixes)

        return {
            "_deeplynx_fsspec_index": True,
            "version": 1,
            "buckets": sorted(index.buckets),
            "entries": entries,
            "directories": directories,
        }


try:
    register_implementation("deeplynx", DeeplynxFileSystem)
except ValueError:
    # Already registered. This is expected if the module is imported multiple times.
    pass
