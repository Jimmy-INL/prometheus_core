"""Tests for IFC artifact rendering."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

if "chainlit" not in sys.modules:
    chainlit = types.ModuleType("chainlit")
    chainlit.CustomElement = object
    sys.modules["chainlit"] = chainlit

from plugins.ifc import render_artifact


def test_render_artifact_localizes_remote_ifc(monkeypatch, tmp_path: Path):
    class _FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self):
            return None

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, uri):
            assert uri == "http://example.test/model.ifc"
            return _FakeResponse(b"IFC DATA")

    async def _fake_process_ifc_upload(path: Path):
        assert path.exists()
        assert path.name == "model.ifc"
        return SimpleNamespace(to_chainlit_element=lambda: "viewer")

    monkeypatch.setattr("plugins.ifc.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr("components.ifc_integration.process_ifc_upload", _fake_process_ifc_upload)

    result = asyncio.run(
        render_artifact(
            {
                "uri": "http://example.test/model.ifc",
                "name": "model.ifc",
                "mime_type": "application/ifc",
            }
        )
    )

    assert result == "viewer"
