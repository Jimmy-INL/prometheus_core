"""Tests for artifact fallback rendering."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from components import message_handler as handler


def test_render_artifacts_downloads_remote_json_file(monkeypatch, tmp_path: Path) -> None:
    created = []

    class DummyFile:
        def __init__(self, *, name: str, path: str, display: str, mime: str = ""):
            self.name = name
            self.path = path
            self.display = display
            self.mime = mime
            created.append(self)

    class _FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, uri: str):
            assert uri == "http://example.test/output.json"
            return _FakeResponse(b'{\"status\":\"ok\"}\n')

    monkeypatch.setattr(handler.cl, "File", DummyFile, raising=False)
    monkeypatch.setattr("components.message_handler.httpx.AsyncClient", _FakeAsyncClient)

    elements, text = asyncio.run(
        handler.render_artifacts(
            [
                {
                    "name": "output.json",
                    "mime_type": "application/json",
                    "uri": "http://example.test/output.json",
                    "description": "Generated ANL JSON intermediate output.",
                }
            ],
            tmp_path,
        )
    )

    assert len(elements) == 1
    assert len(created) == 1
    assert created[0].name == "output.json"
    assert Path(created[0].path).exists()
    assert "Generated ANL JSON intermediate output." in text


def test_render_artifacts_treats_step_as_downloadable_file(monkeypatch, tmp_path: Path) -> None:
    created = []

    class DummyFile:
        def __init__(self, *, name: str, path: str, display: str, mime: str = ""):
            self.name = name
            self.path = path
            self.display = display
            self.mime = mime
            created.append(self)

    monkeypatch.setattr(handler.cl, "File", DummyFile, raising=False)

    async def _no_plugin(artifact):
        return None

    monkeypatch.setattr(handler._plugins, "render_artifact", _no_plugin)

    step_file = tmp_path / "bracket.stp"
    step_file.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n")

    elements, text = asyncio.run(
        handler.render_artifacts(
            [
                {
                    "name": "bracket.stp",
                    "mime_type": "model/step",
                    "uri": f"file://{step_file}",
                    "description": "STEP CAD model.",
                }
            ],
            tmp_path,
        )
    )

    assert len(elements) == 1
    assert created[0].name == "bracket.stp"
    assert created[0].mime == "model/step"
    assert "no viewer available" not in text


def test_render_artifacts_adds_download_for_plugin_viewer(monkeypatch, tmp_path: Path) -> None:
    created = []
    viewer = SimpleNamespace(name="ExodusViewer")

    class DummyFile:
        def __init__(self, *, name: str, path: str, display: str, mime: str = ""):
            self.name = name
            self.path = path
            self.display = display
            self.mime = mime
            created.append(self)

    async def _viewer_plugin(artifact):
        return viewer

    monkeypatch.setattr(handler.cl, "File", DummyFile, raising=False)
    monkeypatch.setattr(handler._plugins, "render_artifact", _viewer_plugin)

    mesh_file = tmp_path / "mesh.e"
    mesh_file.write_bytes(b"exodus")

    elements, text = asyncio.run(
        handler.render_artifacts(
            [
                {
                    "name": "mesh.e",
                    "mime_type": "application/x-exodus",
                    "uri": f"file://{mesh_file}",
                }
            ],
            tmp_path,
        )
    )

    assert text == ""
    assert elements[0] is viewer
    assert elements[1] is created[0]
    assert created[0].name == "mesh.e"
    assert created[0].path == str(mesh_file)


def test_render_artifacts_adds_download_for_inline_json(monkeypatch, tmp_path: Path) -> None:
    created_files = []
    created_viewers = []

    class DummyFile:
        def __init__(self, *, name: str, path: str, display: str, mime: str = ""):
            self.name = name
            self.path = path
            self.display = display
            self.mime = mime
            created_files.append(self)

    class DummyCustomElement:
        def __init__(self, *, name: str, display: str, props: dict):
            self.name = name
            self.display = display
            self.props = props
            created_viewers.append(self)

    async def _no_plugin(artifact):
        return None

    monkeypatch.setattr(handler.cl, "File", DummyFile, raising=False)
    monkeypatch.setattr(handler.cl, "CustomElement", DummyCustomElement, raising=False)
    monkeypatch.setattr(handler._plugins, "render_artifact", _no_plugin)

    elements, text = asyncio.run(
        handler.render_artifacts(
            [
                {
                    "name": "result",
                    "mime_type": "application/json",
                    "json_body": {"status": "ok"},
                }
            ],
            tmp_path,
        )
    )

    assert text == ""
    assert elements == [created_viewers[0], created_files[0]]
    assert created_files[0].name == "result.json"
    assert created_files[0].mime == "application/json"
    assert json.loads(Path(created_files[0].path).read_text()) == {"status": "ok"}
