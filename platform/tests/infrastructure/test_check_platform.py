# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Unit tests for scripts/check_platform.py against a local stub HTTP server."""

import importlib.util
import json
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load_check_platform():
    # The script imports init_env by name, as running it from scripts/ allows
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("check_platform", SCRIPTS / "check_platform.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = _load_check_platform()


@pytest.fixture
def server():
    """A stub server; set ``routes[path] = (status, body)``. Unknown paths answer 404."""
    routes: dict[str, tuple[int, bytes]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = routes.get(self.path, (404, b""))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    # A short poll interval keeps shutdown() from waiting the default 0.5s
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    httpd.routes = routes
    httpd.port = httpd.server_address[1]
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _agents(*names):
    return 200, json.dumps([{"agent_name": n} for n in names]).encode()


def _agent_dir(tmp_path, name):
    d = tmp_path / name.lower().replace(" ", "_")
    d.mkdir()
    (d / "agent_card.json").write_text(json.dumps({"name": name}))
    return d


def _run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["check_platform.py", "--interval", "0", *args])
    return cp.main()


def test_registry_name_matches_the_sdk(tmp_path):
    assert cp.registry_name(_agent_dir(tmp_path, "Thermal Analysis Agent")) == "thermal-analysis-agent"


def test_env_value_prefers_environment_then_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FROM_FILE=file\nBOTH=file\nBLANK=\n")
    monkeypatch.setattr(cp, "ENV", env)
    monkeypatch.setenv("BOTH", "environ")
    monkeypatch.delenv("FROM_FILE", raising=False)
    monkeypatch.delenv("BLANK", raising=False)
    assert cp.env_value("BOTH") == "environ"
    assert cp.env_value("FROM_FILE") == "file"
    assert cp.env_value("BLANK", "default") == "default"
    assert cp.env_value("MISSING") is None


def test_env_value_without_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "ENV", tmp_path / "missing.env")
    monkeypatch.delenv("MISSING", raising=False)
    assert cp.env_value("MISSING", "default") == "default"


def test_registered_skips_malformed_entries(server):
    server.routes["/v1/agents"] = (200, json.dumps([{"agent_name": "a"}, {"agent_name": None}, {}, 1, "b"]).encode())
    assert cp.registered(f"http://127.0.0.1:{server.port}/v1/agents", "key") == {"a"}


def test_registered_rejects_a_non_list_body(server):
    server.routes["/v1/agents"] = (200, b'{"detail": "x"}')
    with pytest.raises(ValueError, match="dict"):
        cp.registered(f"http://127.0.0.1:{server.port}/v1/agents", "key")


@pytest.mark.parametrize("status", [401, 403])
def test_registered_raises_auth_error_on_a_rejected_key(server, status):
    server.routes["/v1/agents"] = (status, b"")
    with pytest.raises(cp.AuthError):
        cp.registered(f"http://127.0.0.1:{server.port}/v1/agents", "key")


def test_registered_raises_http_error_on_other_statuses(server):
    server.routes["/v1/agents"] = (500, b"")
    with pytest.raises(urllib.error.HTTPError):
        cp.registered(f"http://127.0.0.1:{server.port}/v1/agents", "key")


def test_agents_check_reports_missing_agents(server):
    server.routes["/v1/agents"] = _agents("a")
    check = cp.agents_check(f"http://127.0.0.1:{server.port}/v1/agents", "key", {"a", "b", "c"})
    assert check() == "not registered: b, c"
    server.routes["/v1/agents"] = _agents("a", "b", "c", "extra")
    assert check() is None


def test_http_check_passes_on_2xx_and_raises_otherwise(server):
    server.routes["/ok"] = (200, b"ok")
    assert cp.http_check(f"http://127.0.0.1:{server.port}/ok")() is None
    with pytest.raises(urllib.error.HTTPError):
        cp.http_check(f"http://127.0.0.1:{server.port}/missing")()


def test_main_passes_when_everything_is_up(server, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "key")
    server.routes.update(
        {
            "/healthz": (200, b"ok"),
            "/": (200, b"<html>"),
            "/api/setup/status": (200, b"{}"),
            "/v1/agents": _agents("client-agent"),
        }
    )
    port = str(server.port)
    rc = _run_main(
        monkeypatch,
        "--backend-port", port, "--frontend-port", port, "--litellm-port", port,
        str(_agent_dir(tmp_path, "Client Agent")),
    )  # fmt: skip
    assert rc == 0
    assert "The platform is up." in capsys.readouterr().out


def test_main_skips_the_frontend_and_agents_when_not_given(server, monkeypatch):
    # No master key needed and no frontend routes: only the backend is checked
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    server.routes["/healthz"] = (200, b"ok")
    port = str(server.port)
    assert _run_main(monkeypatch, "--backend-port", port, "--litellm-port", port) == 0


def test_main_times_out_and_names_what_failed(server, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "key")
    server.routes.update({"/": (200, b"<html>"), "/api/setup/status": (502, b""), "/v1/agents": _agents()})
    port = str(server.port)
    rc = _run_main(
        monkeypatch,
        "--timeout", "0",
        "--backend-port", port, "--frontend-port", port, "--litellm-port", port,
        str(_agent_dir(tmp_path, "Client Agent")),
    )  # fmt: skip
    assert rc == 1
    err = capsys.readouterr().err
    assert "backend: HTTP Error 404" in err
    assert "frontend /api proxy: HTTP Error 502" in err
    assert "not registered: client-agent" in err
    assert "  frontend:" not in err


def test_main_fails_fast_on_a_rejected_master_key(server, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "wrong")
    server.routes.update({"/healthz": (200, b"ok"), "/v1/agents": (401, b"")})
    port = str(server.port)
    start = time.monotonic()
    rc = _run_main(
        monkeypatch,
        "--timeout", "5",
        "--backend-port", port, "--litellm-port", port,
        str(_agent_dir(tmp_path, "Client Agent")),
    )  # fmt: skip
    assert rc == 1
    assert "rejected LITELLM_MASTER_KEY" in capsys.readouterr().err
    assert time.monotonic() - start < 5, "should exit on the first poll, not wait out the timeout"


def test_main_requires_the_master_key_for_agents(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.setattr(cp, "ENV", tmp_path / "missing.env")
    rc = _run_main(
        monkeypatch, "--backend-port", "1", "--litellm-port", "1", str(_agent_dir(tmp_path, "Client Agent"))
    )
    assert rc == 1
    assert "LITELLM_MASTER_KEY is not set" in capsys.readouterr().err
