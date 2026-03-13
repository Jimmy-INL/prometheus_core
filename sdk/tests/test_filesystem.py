"""Unit tests for DeepLynx fsspec filesystem."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from prometheus_api.storage_client import ConnectionConfig
from prometheus_api.storage_client.filesystem import DeeplynxFileSystem
from prometheus_api.storage_client.models.file import FileMetadata


class _FakeResponse:
    """Minimal response object matching the subset used by filesystem code."""

    def __init__(self, payload: Optional[Any] = None, content: bytes = b""):
        self._payload = payload
        self.content = content

    def json(self) -> Any:
        return self._payload


class _FakeItems:
    """In-memory stand-in for ``StorageClient.items``."""

    def __init__(self, client: "_FakeStorageClient"):
        self._client = client

    def create(self, item) -> SimpleNamespace:
        record_id = self._client._next_id()
        record = {
            "id": record_id,
            "name": item.name,
            "description": item.description,
            "originalId": item.original_id,
            "properties": deepcopy(item.properties),
        }
        self._client.records[record_id] = record
        return SimpleNamespace(id=record_id)

    def update(self, item_id: int, update) -> SimpleNamespace:
        if item_id not in self._client.records:
            raise FileNotFoundError(item_id)
        record = self._client.records[item_id]
        if update.properties is not None:
            record["properties"] = deepcopy(update.properties)
        if update.name is not None:
            record["name"] = update.name
        if update.description is not None:
            record["description"] = update.description
        if update.original_id is not None:
            record["originalId"] = update.original_id
        return SimpleNamespace(id=item_id)


class _FakeFiles:
    """In-memory stand-in for ``StorageClient.files``."""

    def __init__(self, client: "_FakeStorageClient"):
        self._client = client

    def upload(
        self, file_path: Path, name: Optional[str] = None, description: Optional[str] = None
    ):
        file_id = self._client._next_id()
        payload = file_path.read_bytes()
        self._client.file_bytes[file_id] = payload
        return FileMetadata(
            id=file_id,
            name=name or file_path.name,
            description=description,
            file_type=None,
            size=len(payload),
            uri=f"deeplynx://raw/{file_id}",
            created_at=None,
            updated_at=None,
        )

    def delete(self, file_id: int) -> None:
        if file_id not in self._client.file_bytes:
            raise FileNotFoundError(file_id)
        del self._client.file_bytes[file_id]
        self._client.deleted_files.append(file_id)


class _FakeStorageClient:
    """Small fake client that mimics the methods used by ``DeeplynxFileSystem``."""

    def __init__(self):
        self.config = SimpleNamespace(organization_id=1, project_id=2)
        self.records: Dict[int, Dict[str, Any]] = {}
        self.file_bytes: Dict[int, bytes] = {}
        self.deleted_files = []
        self._counter = 100
        self.items = _FakeItems(self)
        self.files = _FakeFiles(self)

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    def _request(self, method: str, path: str, **kwargs) -> _FakeResponse:
        if method == "GET" and path.endswith("/records"):
            params = kwargs.get("params", {})
            page = int(params.get("page", 1))
            limit = int(params.get("limit", 100))
            records = [self.records[k] for k in sorted(self.records)]
            start = max(0, (page - 1) * limit)
            end = start + limit
            return _FakeResponse(payload=deepcopy(records[start:end]))

        if method == "GET" and "/files/" in path:
            file_id = int(path.rsplit("/", 1)[-1])
            if file_id not in self.file_bytes:
                raise FileNotFoundError(file_id)
            return _FakeResponse(content=self.file_bytes[file_id])

        raise NotImplementedError((method, path))


@pytest.fixture
def fake_client():
    """Provide a fresh isolated fake client for each test."""
    return _FakeStorageClient()


def test_constructor_with_client(fake_client):
    """Filesystem should accept caller-managed clients unchanged."""
    fs = DeeplynxFileSystem(client=fake_client)
    assert fs._client is fake_client
    assert fs._owns_client is False


def test_constructor_with_config_builds_owned_client(monkeypatch):
    """Filesystem should lazily create and own a client when config is given."""
    import prometheus_api.storage_client.filesystem as fs_module

    events = []

    class DummyStorageClient:
        def __init__(self, config):
            self.config = config
            events.append("init")

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")

    monkeypatch.setattr(fs_module, "StorageClient", DummyStorageClient)

    config = ConnectionConfig(organization_id=1, project_id=2, jwt_token="token")
    fs = fs_module.DeeplynxFileSystem(config=config)
    assert events == []

    _ = fs._client_or_raise()
    assert events == ["init", "enter"]

    fs.close()
    assert events == ["init", "enter", "exit"]


def test_constructor_defaults_to_from_env(monkeypatch):
    """When both config/client are absent, ``ConnectionConfig.from_env`` is used."""
    import prometheus_api.storage_client.filesystem as fs_module

    events = []
    config = ConnectionConfig(organization_id=1, project_id=2, jwt_token="token")

    class DummyStorageClient:
        def __init__(self, supplied):
            assert supplied == config
            events.append("init")
            self.config = supplied

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")

    monkeypatch.setattr(fs_module.ConnectionConfig, "from_env", lambda: config)
    monkeypatch.setattr(fs_module, "StorageClient", DummyStorageClient)

    fs = fs_module.DeeplynxFileSystem(skip_instance_cache=True)
    _ = fs._client_or_raise()
    fs.close()

    assert events == ["init", "enter", "exit"]


def test_constructor_with_both_client_and_config_raises(fake_client):
    """Passing both config and client should fail fast."""
    config = ConnectionConfig(organization_id=1, project_id=2, jwt_token="token")
    with pytest.raises(ValueError, match="either config or client"):
        DeeplynxFileSystem(config=config, client=fake_client)


def test_constructor_env_errors_propagate(monkeypatch):
    """Errors from env-based config loading should bubble to the caller."""
    import prometheus_api.storage_client.filesystem as fs_module

    class DummyConnectionConfig:
        @classmethod
        def from_env(cls):
            raise ValueError("missing env")

    monkeypatch.setattr(fs_module, "ConnectionConfig", DummyConnectionConfig)
    with pytest.raises(ValueError, match="missing env"):
        fs_module.DeeplynxFileSystem(skip_instance_cache=True)


def test_strip_protocol_and_split_path(fake_client):
    """Protocol stripping and bucket/key splitting should normalize consistently."""
    fs = DeeplynxFileSystem(client=fake_client)
    assert DeeplynxFileSystem._strip_protocol("deeplynx://bucket/a/b/") == "bucket/a/b"
    assert fs._split_path("bucket/path/to.obj") == ("bucket", "path/to.obj")
    with pytest.raises(ValueError, match="Path must include a bucket"):
        fs._split_path("/")


def test_index_created_when_missing(fake_client):
    """First filesystem operation should bootstrap an index record when missing."""
    fs = DeeplynxFileSystem(client=fake_client)
    assert fs.ls("", detail=False) == []
    assert len(fake_client.records) == 1
    created = list(fake_client.records.values())[0]
    assert created["originalId"] == "deeplynx-fsspec-index"
    assert created["properties"]["_deeplynx_fsspec_index"] is True


def test_write_read_exists_info(fake_client):
    """Basic write/read path should populate metadata and info correctly."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("deeplynx://bucket/data.bin", b"\x01\x02\x03")

    assert fs.cat_file("bucket/data.bin") == b"\x01\x02\x03"
    assert fs.exists("bucket/data.bin")
    assert fs.isfile("bucket/data.bin")
    assert fs.isdir("bucket")

    info = fs.info("bucket/data.bin")
    assert info["type"] == "file"
    assert info["size"] == 3
    assert "record_id" in info


def test_put_and_get_single_file_hooks(fake_client, tmp_path):
    """put/get hooks should publish to and stage from DeepLynx paths."""
    fs = DeeplynxFileSystem(client=fake_client)
    local_source = tmp_path / "source.dat"
    local_source.write_bytes(b"publish-payload")

    # Publish a local file into the virtual object namespace.
    fs.put(str(local_source), "deeplynx://bucket/stage/source.dat")
    assert fs.cat_file("deeplynx://bucket/stage/source.dat") == b"publish-payload"

    # Stage it back locally using the complementary get hook.
    local_staged = tmp_path / "staged.dat"
    fs.get("deeplynx://bucket/stage/source.dat", str(local_staged))
    assert local_staged.read_bytes() == b"publish-payload"


def test_put_and_get_multiple_files_hooks(fake_client, tmp_path):
    """put/get should support list inputs for multi-entity batch workflows."""
    fs = DeeplynxFileSystem(client=fake_client)
    local_a = tmp_path / "a.txt"
    local_b = tmp_path / "b.txt"
    local_a.write_text("alpha")
    local_b.write_text("beta")

    remote_paths = ["deeplynx://bucket/batch/a.txt", "deeplynx://bucket/batch/b.txt"]
    fs.put([str(local_a), str(local_b)], remote_paths)
    assert fs.cat_file("deeplynx://bucket/batch/a.txt") == b"alpha"
    assert fs.cat_file("deeplynx://bucket/batch/b.txt") == b"beta"

    staged_a = tmp_path / "staged-a.txt"
    staged_b = tmp_path / "staged-b.txt"
    fs.get(remote_paths, [str(staged_a), str(staged_b)])
    assert staged_a.read_text() == "alpha"
    assert staged_b.read_text() == "beta"


def test_atomic_overwrite_deletes_replaced_record(fake_client):
    """Overwrite should repoint index and best-effort delete prior record."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("bucket/replace.txt", b"first")
    first_record = fs.info("bucket/replace.txt")["record_id"]

    fs.pipe_file("bucket/replace.txt", b"second")
    second_record = fs.info("bucket/replace.txt")["record_id"]

    assert second_record != first_record
    assert first_record in fake_client.deleted_files
    assert fs.cat_file("bucket/replace.txt") == b"second"


def test_exclusive_create_and_append(fake_client):
    """Exclusive-create should fail on existing keys and append should preserve data."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("bucket/object.txt", b"hello")
    with pytest.raises(FileExistsError):
        fs.pipe_file("bucket/object.txt", b"nope", mode="create")

    with fs.open("bucket/object.txt", "ab") as fp:
        fp.write(b" world")
    assert fs.cat_file("bucket/object.txt") == b"hello world"


def test_listing_and_directory_info(fake_client):
    """Listings should show root buckets and derived prefix directories."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("bucket/root.txt", b"a")
    fs.pipe_file("bucket/folder/nested.txt", b"b")

    assert fs.ls("", detail=False) == ["bucket"]
    bucket_listing = fs.ls("bucket", detail=False)
    assert "bucket/root.txt" in bucket_listing
    assert "bucket/folder" in bucket_listing
    assert fs.ls("bucket/folder", detail=False) == ["bucket/folder/nested.txt"]
    assert fs.info("bucket/folder")["type"] == "directory"


def test_rm_file_and_recursive_rm(fake_client):
    """File and recursive directory deletions should update index and backend."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("bucket/dir/a.txt", b"a")
    fs.pipe_file("bucket/dir/sub/b.txt", b"b")

    fs.rm_file("bucket/dir/a.txt")
    assert not fs.exists("bucket/dir/a.txt")

    fs.rm("bucket/dir", recursive=True)
    assert not fs.exists("bucket/dir/sub/b.txt")
    assert not fs.exists("bucket/dir")

    fs.rm("bucket", recursive=True)
    assert not fs.exists("bucket")


def test_mkdir_and_makedirs_placeholders(fake_client):
    """mkdir/makedirs should create persistent virtual directory placeholders."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.mkdir("bucket")
    fs.makedirs("bucket/a/b", exist_ok=True)

    assert fs.isdir("bucket")
    assert fs.isdir("bucket/a")
    assert fs.isdir("bucket/a/b")
    assert "bucket/a" in fs.ls("bucket", detail=False)


def test_invalidate_cache_reloads_index(fake_client):
    """Cache invalidation should force index reload from underlying record state."""
    fs = DeeplynxFileSystem(client=fake_client)
    fs.pipe_file("bucket/object.txt", b"payload")
    assert fs.exists("bucket/object.txt")

    index_id = fs._load_index().record_id
    props = fake_client.records[index_id]["properties"]
    props["entries"] = {}
    props["buckets"] = []

    assert fs.exists("bucket/object.txt")
    fs.invalidate_cache()
    assert not fs.exists("bucket/object.txt")
