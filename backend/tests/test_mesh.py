"""Tests for the mesh (Exodus/STL → VTP) restoration.

Most tests are offline (no VTK): the json_body/prop shape, the source-kind picker,
the enrichment hook (with the VTK conversion + URI resolver stubbed), and the VTP
route (auth / 404 / path-traversal, serving a pre-seeded cache file). The converter
round-trip is guarded by ``pytest.importorskip("vtk")`` so it runs only where VTK is
installed (the container), never breaking the offline suite.
"""

import json
import pickle
import types
from concurrent import futures
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import uri_resolver
from app.services.mesh import service


# --------------------------------------------------------------------------- #
# _mesh_kind — STL vs Exodus dispatch
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,uri,mime,expected",
    [
        ("mesh.stl", "", "", "stl"),
        ("", "file:///data/model.STL", "", "stl"),  # extension is case-insensitive
        ("", "", "model/stl", "stl"),
        ("", "", "application/vnd.ms-pki.stl", "stl"),
        ("mesh.exo", "", "", "exodus"),
        ("mesh.e", "", "", "exodus"),
        ("data", "", "application/x-exodus", "exodus"),
        ("", "", "", "exodus"),  # default
        # extension wins over a mismatched mime
        ("mesh.stl", "", "application/x-exodus", "stl"),
    ],
)
def test_mesh_kind(name, uri, mime, expected):
    assert service._mesh_kind(name, uri, mime) == expected


# --------------------------------------------------------------------------- #
# _build_json_body — the exact prop shape MeshViewerElement.tsx reads
# --------------------------------------------------------------------------- #


def _manifest(point=None, cell=None):
    return {
        "version": "1.0",
        "num_timesteps": 1,
        "files": [{"index": 0, "timestep_index": 0, "time_value": 0.0, "filename": "surface_t0000.vtp"}],
        "variables": {"point": point or [], "cell": cell or []},
        "array_ranges": {},
        "bounds": [0, 1, 0, 1, 0, 1],
    }


def test_build_json_body_shape_and_baseurl():
    metadata = {"num_timesteps": 2, "time_values": [0.0, 1.0]}
    body = service._build_json_body("ds123", _manifest(point=["temperature"], cell=["block_id"]), metadata, "My Mesh")

    assert body["datasetId"] == "ds123"
    assert body["baseUrl"] == "/api/artifacts/mesh/ds123"
    assert body["baseUrl"] == f"{service.MESH_URL_PREFIX}/ds123"
    assert body["title"] == "My Mesh"
    assert body["metadata"] is metadata
    assert body["manifest"]["files"][0]["filename"] == "surface_t0000.vtp"
    assert body["initialColorPreset"] == "coolToWarm"
    assert body["showControls"] is True
    assert body["allowPicking"] is True


def test_build_json_body_initial_variable_prefers_point_then_cell_then_none():
    m = {"num_timesteps": 1, "time_values": [0.0]}
    assert service._build_json_body("d", _manifest(point=["p1"], cell=["c1"]), m, "t")["initialVariable"] == "p1"
    assert service._build_json_body("d", _manifest(cell=["c1"]), m, "t")["initialVariable"] == "c1"
    assert service._build_json_body("d", _manifest(), m, "t")["initialVariable"] is None


# --------------------------------------------------------------------------- #
# enrich_mesh_artifacts — the turn-time hook (VTK + resolver stubbed)
# --------------------------------------------------------------------------- #


def _stub_resolver(monkeypatch, tmp_path):
    """Make resolve_to_local_path return a real (existing) local file."""
    src = tmp_path / "mesh.exo"
    src.write_bytes(b"fake-exodus-bytes")

    async def _resolve(uri, *, cache_dir, artifact=None, artifact_id=None):
        return src

    monkeypatch.setattr(uri_resolver, "resolve_to_local_path", _resolve)
    return src


async def test_enrich_populates_mesh_json_body(monkeypatch, tmp_path):
    _stub_resolver(monkeypatch, tmp_path)

    calls = []

    async def _fake_convert(local_path, cache_root, name, uri, mime, *, ident):
        calls.append((name, mime))
        return "dsAAA", _manifest(point=["temperature"]), {"num_timesteps": 1, "time_values": [0.0]}

    monkeypatch.setattr(service, "_convert_offloop", _fake_convert)

    art = {"artifact_id": "m1", "name": "mesh.exo", "mime_type": "application/x-exodus", "uri": "file:///x/mesh.exo"}
    response = types.SimpleNamespace(new_artifacts=[art], artifacts=[art])

    await service.enrich_mesh_artifacts(response)

    assert calls  # conversion actually ran
    assert art["json_body"] is not None
    assert art["json_body"]["datasetId"] == "dsAAA"
    assert art["json_body"]["baseUrl"] == "/api/artifacts/mesh/dsAAA"
    assert art["json_body"]["initialVariable"] == "temperature"


async def test_enrich_applies_body_to_all_objects_sharing_identity(monkeypatch, tmp_path):
    # new_artifacts and the persisted catalog can be distinct dict objects for the same
    # artifact; both must end up carrying the manifest.
    _stub_resolver(monkeypatch, tmp_path)

    async def _fake_convert(*a, **kw):
        return "ds1", _manifest(), {"num_timesteps": 1, "time_values": [0.0]}

    monkeypatch.setattr(service, "_convert_offloop", _fake_convert)

    new_obj = {"artifact_id": "same", "name": "a.exo", "mime_type": "application/x-exodus", "uri": "file:///a.exo"}
    cat_obj = {"artifact_id": "same", "name": "a.exo", "mime_type": "application/x-exodus", "uri": "file:///a.exo"}
    response = types.SimpleNamespace(new_artifacts=[new_obj], artifacts=[cat_obj])

    await service.enrich_mesh_artifacts(response)

    assert new_obj["json_body"] is not None
    assert cat_obj["json_body"] is not None  # distinct object, same identity → enriched


async def test_enrich_leaves_non_mesh_untouched(monkeypatch, tmp_path):
    _stub_resolver(monkeypatch, tmp_path)

    async def _boom(*a, **kw):
        raise AssertionError("conversion must not run for a non-mesh artifact")

    monkeypatch.setattr(service, "_convert_offloop", _boom)

    art = {"artifact_id": "p1", "name": "report.pdf", "mime_type": "application/pdf", "uri": "file:///r.pdf"}
    response = types.SimpleNamespace(new_artifacts=[art], artifacts=[art])

    await service.enrich_mesh_artifacts(response)

    assert art.get("json_body") is None


async def test_enrich_downgrades_gracefully_on_conversion_failure(monkeypatch, tmp_path):
    _stub_resolver(monkeypatch, tmp_path)

    async def _fail(*a, **kw):
        raise RuntimeError("vtk blew up")

    monkeypatch.setattr(service, "_convert_offloop", _fail)

    art = {"artifact_id": "m2", "name": "mesh.exo", "mime_type": "application/x-exodus", "uri": "file:///x.exo"}
    response = types.SimpleNamespace(new_artifacts=[art], artifacts=[art])

    await service.enrich_mesh_artifacts(response)  # must not raise

    assert art.get("json_body") is None  # left null → frontend downgrades to a download


async def test_enrich_skips_mesh_without_uri(monkeypatch):
    async def _boom(*a, **kw):
        raise AssertionError("conversion must not run without a resolvable uri")

    monkeypatch.setattr(service, "_convert_offloop", _boom)

    art = {"artifact_id": "m3", "name": "mesh.exo", "mime_type": "application/x-exodus"}  # no uri
    response = types.SimpleNamespace(new_artifacts=[art], artifacts=[art])

    await service.enrich_mesh_artifacts(response)

    assert art.get("json_body") is None


# --------------------------------------------------------------------------- #
# _convert_offloop — subprocess-pool crash + timeout containment
# --------------------------------------------------------------------------- #


class _FakeProc:
    """Stand-in for a ProcessPoolExecutor worker process."""

    def __init__(self) -> None:
        self.killed = False

    def is_alive(self) -> bool:
        return not self.killed

    def kill(self) -> None:
        self.killed = True


class _FakeExecutor:
    """Minimal executor: `run_in_executor` only needs `.submit()` returning a Future.

    `_processes` mirrors ProcessPoolExecutor's private worker map, which
    `_discard_executor(kill_children=True)` reaches into to stop a wedged conversion.
    """

    def __init__(self, future: futures.Future) -> None:
        self._future = future
        self._processes = {1: _FakeProc()}
        self.shutdown_calls: list[dict] = []

    def submit(self, fn, *args):
        return self._future

    def shutdown(self, wait=True, cancel_futures=False):
        self.shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})


async def test_convert_offloop_survives_a_dead_worker(monkeypatch, tmp_path):
    """A child segfault/OOM must cost one artifact, not the web process."""
    future: futures.Future = futures.Future()
    future.set_running_or_notify_cancel()
    future.set_exception(BrokenProcessPool("worker died"))
    fake = _FakeExecutor(future)
    monkeypatch.setattr(service, "_vtk_executor", fake)

    result = await service._convert_offloop(tmp_path / "m.exo", tmp_path, "m.exo", "file:///m.exo", "", ident="m1")

    assert result is None  # degrades, does not raise
    # The pool is poisoned for every later submit, so it must be replaced, not reused.
    assert service._vtk_executor is None
    assert fake.shutdown_calls == [{"wait": False, "cancel_futures": True}]
    # A dead worker needs no killing; only the timeout path does that.
    assert fake._processes[1].killed is False


async def test_convert_offloop_times_out_and_kills_the_pool(monkeypatch, tmp_path):
    """A wedged conversion can't be cancelled cooperatively, so the workers are killed."""
    fake = _FakeExecutor(futures.Future())  # never completes
    monkeypatch.setattr(service, "_vtk_executor", fake)
    monkeypatch.setattr(service.settings, "mesh_timeout_seconds", 0.05, raising=False)

    result = await service._convert_offloop(tmp_path / "m.exo", tmp_path, "m.exo", "file:///m.exo", "", ident="m2")

    assert result is None
    assert service._vtk_executor is None
    assert fake._processes[1].killed is True
    assert fake.shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_shutdown_mesh_executor_is_a_noop_when_unused(monkeypatch):
    """The lifespan calls this unconditionally; a server that converted nothing has no pool."""
    monkeypatch.setattr(service, "_vtk_executor", None)
    service.shutdown_mesh_executor()  # must not raise
    assert service._vtk_executor is None


def test_convert_sync_crosses_the_process_boundary():
    """Guard the contract the process pool depends on: the callable is picklable by
    reference and every argument survives a pickle round-trip. A future refactor that
    closes `_convert_sync` over something unpicklable would otherwise only fail at
    runtime, inside a submit, as a degraded artifact."""
    assert pickle.loads(pickle.dumps(service._convert_sync)) is service._convert_sync
    args = (Path("/tmp/mesh.exo"), Path("/var/cache/prometheus-mesh"), "mesh.exo", "file:///mesh.exo", "")
    assert pickle.loads(pickle.dumps(args)) == args


# --------------------------------------------------------------------------- #
# GET /api/artifacts/mesh/{dataset_id}/{filename}
# --------------------------------------------------------------------------- #


def _authed_client(monkeypatch, tmp_path) -> TestClient:
    """TestClient with a valid session cookie and the mesh cache root at tmp_path."""
    from app import security
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(security.settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "mesh_cache_dir", str(tmp_path), raising=False)

    token = security.issue_token(security.User(identifier="alice"), sid="sid-mesh")
    client = TestClient(app)
    client.cookies.set(settings.cookie_name, token)
    return client


def test_mesh_route_requires_auth(tmp_path, monkeypatch):
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "mesh_cache_dir", str(tmp_path), raising=False)
    client = TestClient(app)
    assert client.get("/api/artifacts/mesh/ds1/surface_t0000.vtp").status_code == 401


def test_mesh_route_serves_cached_vtp(monkeypatch, tmp_path):
    ds = tmp_path / "ds1"
    ds.mkdir()
    (ds / "surface_t0000.vtp").write_text("<VTKFile type='PolyData'></VTKFile>")

    client = _authed_client(monkeypatch, tmp_path)
    resp = client.get("/api/artifacts/mesh/ds1/surface_t0000.vtp")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "VTKFile" in resp.text


def test_mesh_route_404_when_missing(monkeypatch, tmp_path):
    client = _authed_client(monkeypatch, tmp_path)
    assert client.get("/api/artifacts/mesh/ds1/surface_t0000.vtp").status_code == 404


def test_mesh_route_rejects_directory_as_file(monkeypatch, tmp_path):
    (tmp_path / "ds1").mkdir()  # exists but is a dir, not a file
    client = _authed_client(monkeypatch, tmp_path)
    assert client.get("/api/artifacts/mesh/ds1/sub").status_code == 404


def test_reject_unsafe_segment_blocks_traversal():
    from fastapi import HTTPException

    from app.routers.artifacts import _reject_unsafe_segment

    # good names pass
    _reject_unsafe_segment("ds1")
    _reject_unsafe_segment("surface_t0000.vtp")

    # traversal / separators / bad chars are rejected with 400
    for bad in ["..", "../etc", "a/b", "a\\b", "..%2f", "foo bar", ""]:
        with pytest.raises(HTTPException) as exc:
            _reject_unsafe_segment(bad)
        assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# Converter round-trip — VTK-only (skipped where VTK isn't installed)
# --------------------------------------------------------------------------- #


def test_stl_conversion_roundtrip_and_cache(tmp_path):
    vtk = pytest.importorskip("vtk")
    from app.services.mesh.stl import convert_stl_sync

    # Synthesize a small binary STL from a sphere.
    sphere = vtk.vtkSphereSource()
    sphere.Update()
    stl_path = tmp_path / "sphere.stl"
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(stl_path))
    writer.SetInputConnection(sphere.GetOutputPort())
    writer.Write()

    out = tmp_path / "out"
    metadata = convert_stl_sync(stl_path, out)

    assert (out / "surface_t0000.vtp").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "meta.json").is_file()
    assert metadata["num_timesteps"] == 1
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["files"][0]["filename"] == "surface_t0000.vtp"
    assert manifest["variables"] == {"point": [], "cell": []}


def test_convert_sync_stl_branch_uses_cache(tmp_path):
    pytest.importorskip("vtk")
    import vtk

    from app.services.mesh.cache import compute_dataset_id

    sphere = vtk.vtkSphereSource()
    sphere.Update()
    stl_path = tmp_path / "sphere.stl"
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(stl_path))
    writer.SetInputConnection(sphere.GetOutputPort())
    writer.Write()

    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    dataset_id, manifest, metadata = service._convert_sync(stl_path, cache_root, "sphere.stl", "", "model/stl")
    assert dataset_id == compute_dataset_id(stl_path, {"type": "stl"})
    assert (cache_root / dataset_id / "surface_t0000.vtp").is_file()
    assert manifest["num_timesteps"] == 1
    assert metadata["num_elements"] > 0

    # Second call is a cache hit (manifest already present) — same id, still valid.
    dataset_id2, _, _ = service._convert_sync(stl_path, cache_root, "sphere.stl", "", "model/stl")
    assert dataset_id2 == dataset_id
