#!/usr/bin/env python3
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

"""End-to-end status-matrix smoke harness for the backend (task 10).

Exercises every wire path against a **running stack** (backend + client-agent +
Redis) without the React app — pure httpx + SSE. Prints ``PASS``/``FAIL``/``WARN``/
``SKIP`` per path and exits non-zero if anything FAILed.

    uv run python scripts/smoke.py --base-url http://localhost:8600

What each result means:

- **FAIL** — a transport/contract defect: non-2xx where 2xx is required, malformed
  JSON, missing ``turn_id``, SSE never opened, etc. These fail the run.
- **WARN** — the path worked but the agent chose a *different* (still valid) status
  than the one this path targets (e.g. a "plan" query came back ``completed``). The
  transport was proven; the exact status is deployment/prompt dependent, so it does
  not fail the run. The actual status is printed.
- **SKIP** — a prerequisite was unavailable (no artifact to fetch, Redis unreachable
  for the synthetic background path, agent never backgrounded), so the path could not
  be attempted.

The ``needs_info`` / ``plan_ready`` / ``backgrounded`` triggers are agent-dependent;
override the queries via ``--*-query`` flags (or ``SMOKE_*_QUERY`` env vars) to match
your deployment's prompts. The **backgrounded** completion can be forced
deterministically via synthetic Redis events (``--synthetic-background``) once a real
turn has registered the task id as awaited — see ``_step_backgrounded``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

# --------------------------------------------------------------------------- #
# Result tracking
# --------------------------------------------------------------------------- #

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"

_COLORS = {PASS: "\033[32m", FAIL: "\033[31m", WARN: "\033[33m", SKIP: "\033[90m"}
_RESET = "\033[0m"


@dataclass
class Results:
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # (path, status, detail)

    def record(self, path: str, status: str, detail: str = "") -> None:
        color = _COLORS.get(status, "") if sys.stdout.isatty() else ""
        reset = _RESET if color else ""
        print(f"  [{color}{status:^4}{reset}] {path}" + (f" — {detail}" if detail else ""))
        self.rows.append((path, status, detail))

    def summary_exit_code(self) -> int:
        counts = {s: sum(1 for _, st, _ in self.rows if st == s) for s in (PASS, FAIL, WARN, SKIP)}
        print(
            f"\nSummary: {counts[PASS]} passed, {counts[FAIL]} failed, {counts[WARN]} warnings, {counts[SKIP]} skipped"
        )
        return 1 if counts[FAIL] else 0


# --------------------------------------------------------------------------- #
# SSE collector — a background thread draining GET /api/events
# --------------------------------------------------------------------------- #


class SSECollector:
    """Streams ``GET /api/events`` on a background thread, parsing typed frames.

    Frames are ``{"event": <name>, "data": <parsed json or raw str>}``. Heartbeat/
    comment lines (``: ping``, ``: connected``) are ignored. ``wait_for`` polls the
    accumulated frames for a predicate match up to a timeout.
    """

    def __init__(self, base_url: str, cookies: httpx.Cookies, verify: bool) -> None:
        self._base_url = base_url
        self._cookies = cookies
        self._verify = verify
        self._frames: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._opened = threading.Event()
        self._error: Optional[str] = None
        self._thread = threading.Thread(target=self._run, name="sse-collector", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            with httpx.Client(base_url=self._base_url, cookies=self._cookies, verify=self._verify, timeout=None) as c:
                with c.stream("GET", "/api/events", headers={"Accept": "text/event-stream"}) as r:
                    if r.status_code != 200:
                        self._error = f"SSE returned HTTP {r.status_code}"
                        self._opened.set()
                        return
                    self._opened.set()
                    event_name: Optional[str] = None
                    data_lines: list[str] = []
                    for line in r.iter_lines():
                        if self._stop.is_set():
                            break
                        if line.startswith(":"):
                            continue  # comment / heartbeat
                        if line == "":
                            if data_lines:
                                self._append(event_name or "message", "\n".join(data_lines))
                            event_name, data_lines = None, []
                            continue
                        if line.startswith("event:"):
                            event_name = line[len("event:") :].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[len("data:") :].lstrip())
        except Exception as exc:  # noqa: BLE001 - surfaced via self._error
            self._error = f"{type(exc).__name__}: {exc}"
            self._opened.set()

    def _append(self, event: str, raw: str) -> None:
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        with self._lock:
            self._frames.append({"event": event, "data": data})

    def wait_opened(self, timeout: float) -> bool:
        return self._opened.wait(timeout) and self._error is None

    @property
    def error(self) -> Optional[str]:
        return self._error

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float,
    ) -> Optional[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < deadline:
            with self._lock:
                frames = self._frames[seen:]
                seen = len(self._frames)
            for frame in frames:
                if predicate(frame):
                    return frame
            time.sleep(0.1)
        return None

    def stop(self) -> None:
        self._stop.set()


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


class Harness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.results = Results()
        self.client = httpx.Client(base_url=args.base_url, verify=args.verify, timeout=args.http_timeout)
        self.conversation_id: Optional[str] = None
        self.sse: Optional[SSECollector] = None
        self.completed_artifacts: list[dict[str, Any]] = []

    # -- low-level helpers --------------------------------------------------- #

    def _chat(self, **body: Any) -> httpx.Response:
        return self.client.post("/api/chat/messages", json=body, timeout=self.args.turn_timeout)

    # -- steps --------------------------------------------------------------- #

    def step_health(self) -> bool:
        try:
            r = self.client.get("/healthz")
        except Exception as exc:  # noqa: BLE001
            self.results.record("healthz", FAIL, f"cannot reach {self.args.base_url}: {exc}")
            return False
        if r.status_code != 200:
            self.results.record("healthz", FAIL, f"HTTP {r.status_code}")
            return False
        self.results.record("healthz", PASS)
        return True

    def step_login(self) -> bool:
        r = self.client.post(
            "/api/auth/login",
            json={"username": self.args.username, "password": self.args.password},
        )
        if r.status_code != 200:
            self.results.record("auth/login", FAIL, f"HTTP {r.status_code}: {r.text[:120]}")
            return False
        if not self.client.cookies.get("prometheus_session"):
            self.results.record("auth/login", FAIL, "no session cookie set")
            return False
        self.results.record("auth/login", PASS, f"user={r.json().get('user', {}).get('identifier', '?')}")
        return True

    def step_me(self) -> bool:
        r = self.client.get("/api/auth/me")
        if r.status_code != 200:
            self.results.record("auth/me", FAIL, f"HTTP {r.status_code}")
            return False
        self.results.record("auth/me", PASS)
        return True

    def step_config(self) -> None:
        r = self.client.get("/api/config")
        if r.status_code != 200:
            self.results.record("config", WARN, f"HTTP {r.status_code}")
            return
        self.results.record("config", PASS, f"max_upload_bytes={r.json().get('max_upload_bytes')}")

    def step_session(self) -> bool:
        r = self.client.post("/api/sessions", json={})
        if r.status_code != 200:
            self.results.record("sessions", FAIL, f"HTTP {r.status_code}: {r.text[:120]}")
            return False
        self.conversation_id = r.json().get("conversation_id")
        if not self.conversation_id:
            self.results.record("sessions", FAIL, "no conversation_id")
            return False
        self.results.record("sessions", PASS, f"conversation_id={self.conversation_id}")
        return True

    def step_open_sse(self) -> bool:
        self.sse = SSECollector(self.args.base_url, self.client.cookies, self.args.verify)
        self.sse.start()
        if not self.sse.wait_opened(self.args.sse_open_timeout):
            self.results.record("events (SSE open)", FAIL, self.sse.error or "did not open in time")
            return False
        self.results.record("events (SSE open)", PASS)
        return True

    def _run_turn(self, path: str, *, expected: set[str], **body: Any) -> Optional[dict[str, Any]]:
        """POST a turn; FAIL on transport/contract errors, WARN on off-target status.

        Returns the parsed response dict (or ``None`` on hard failure).
        """
        try:
            r = self._chat(**body)
        except Exception as exc:  # noqa: BLE001
            self.results.record(path, FAIL, f"request error: {exc}")
            return None
        if r.status_code != 200:
            self.results.record(path, FAIL, f"HTTP {r.status_code}: {r.text[:120]}")
            return None
        data = r.json()
        turn_id, status = data.get("turn_id"), data.get("status")
        if not turn_id:
            self.results.record(path, FAIL, "response missing turn_id")
            return None
        if status not in expected:
            self.results.record(path, WARN, f"got status={status!r} (wanted one of {sorted(expected)})")
        else:
            self.results.record(path, PASS, f"status={status}")
        return data

    def step_simple_turn(self) -> None:
        data = self._run_turn(
            "chat (simple → completed/answer)",
            expected={"completed", "answer", "recommendation"},
            query=self.args.simple_query,
        )
        if not data:
            return
        # Capture artifacts for the content-proxy step.
        self.completed_artifacts = data.get("artifacts") or []
        # Status frames should have streamed with the matching turn_id.
        turn_id = data["turn_id"]
        frame = (
            self.sse.wait_for(
                lambda f: (
                    f["event"] == "status" and isinstance(f["data"], dict) and f["data"].get("turn_id") == turn_id
                ),
                timeout=self.args.sse_frame_timeout,
            )
            if self.sse
            else None
        )
        if frame:
            self.results.record("chat status SSE frames", PASS, f"turn_id={turn_id}")
        else:
            # Not all deployments stream progress for trivial queries.
            self.results.record("chat status SSE frames", WARN, "no status frame observed for turn")

    def step_needs_info(self) -> None:
        data = self._run_turn(
            "chat (needs_info)",
            expected={"needs_info"},
            query=self.args.needs_info_query,
        )
        if not data or data.get("status") != "needs_info":
            return
        questions = data.get("followup_questions") or []
        if not questions:
            self.results.record("needs_info followup shape", FAIL, "needs_info without followup_questions")
            return
        self.results.record("needs_info followup shape", PASS, f"{len(questions)} field(s)")
        # Answer the first field with a placeholder and re-POST — should progress.
        answers = {q.get("id"): (q.get("default") or "SS316") for q in questions if q.get("id")}
        followup = self._run_turn(
            "chat (needs_info → answered)",
            expected={"completed", "answer", "recommendation", "plan_ready", "needs_info", "executing"},
            followup_answers=answers,
        )
        if followup:
            self.results.record("needs_info round-trip", PASS, f"progressed to status={followup.get('status')}")

    def step_plan(self) -> None:
        data = self._run_turn(
            "chat (plan_ready)",
            expected={"plan_ready"},
            query=self.args.plan_query,
        )
        if not data or data.get("status") != "plan_ready":
            return
        if data.get("plan") is None:
            self.results.record("plan_ready payload", FAIL, "plan_ready without plan")
        else:
            self.results.record("plan_ready payload", PASS, f"auto_approve={data.get('auto_approve')}")
        # Approve in this conversation.
        approved = self._run_turn(
            "chat (plan_approved)",
            expected={"completed", "answer", "recommendation", "executing", "backgrounded"},
            plan_approved=True,
        )
        if approved:
            self.results.record("plan approve round-trip", PASS, f"status={approved.get('status')}")
        # Reject requires a fresh plan in a new conversation.
        self._plan_reject_in_new_session()

    def _plan_reject_in_new_session(self) -> None:
        r = self.client.post("/api/sessions", json={})
        if r.status_code != 200:
            self.results.record("plan reject (new session)", SKIP, "could not start new session")
            return
        self.conversation_id = r.json().get("conversation_id")
        data = self._run_turn(
            "chat (plan_ready for reject)",
            expected={"plan_ready"},
            query=self.args.plan_query,
        )
        if not data or data.get("status") != "plan_ready":
            self.results.record("plan reject round-trip", SKIP, "did not reach a second plan_ready")
            return
        rejected = self._run_turn(
            "chat (plan_rejected)",
            expected={"completed", "answer", "error", "executing"},
            plan_rejected=True,
        )
        if rejected:
            self.results.record("plan reject round-trip", PASS, f"status={rejected.get('status')}")

    def step_backgrounded(self) -> None:
        data = self._run_turn(
            "chat (backgrounded)",
            expected={"backgrounded"},
            query=self.args.background_query,
        )
        if not data:
            return
        if data.get("status") != "backgrounded":
            self.results.record("backgrounded task_done SSE", SKIP, "agent did not background this query")
            return
        task_id = data.get("task_id")
        if not task_id:
            self.results.record("backgrounded task_done SSE", FAIL, "backgrounded without task_id")
            return
        # Optionally force deterministic completion via synthetic Redis events. The
        # session already registered task_id as awaited (map_backgrounded), so the
        # SSE subscriber will relay a synthetic terminal event for it.
        if self.args.synthetic_background:
            if not self._publish_synthetic_completion(task_id):
                self.results.record("backgrounded task_done SSE", SKIP, "Redis unavailable for synthetic completion")
                return
        frame = (
            self.sse.wait_for(
                lambda f: (
                    f["event"] == "task_done" and isinstance(f["data"], dict) and f["data"].get("task_id") == task_id
                ),
                timeout=self.args.background_timeout,
            )
            if self.sse
            else None
        )
        if frame:
            state = frame["data"].get("state")
            self.results.record("backgrounded task_done SSE", PASS, f"task_id={task_id} state={state}")
        else:
            self.results.record(
                "backgrounded task_done SSE",
                WARN,
                "no task_done frame (task may still be running; try --synthetic-background)",
            )

    def _publish_synthetic_completion(self, task_id: str) -> bool:
        """Persist a canned result and publish a terminal event on the task channel.

        Mirrors what the client-agent does on background-task completion (task 05):
        result under ``tasks:result:{conv}:{task_id}``, terminal event on
        ``tasks:events:{conv}``. Returns ``False`` when Redis can't be reached.
        """
        try:
            import redis  # redis-py (sync) — a backend dependency
        except Exception:
            return False
        try:
            r = redis.from_url(self.args.redis_url, decode_responses=True)
            result = {
                "conversation_id": self.conversation_id,
                "status": "completed",
                "report": "Synthetic background result (smoke harness).",
                "message": "Background task complete.",
            }
            r.set(f"tasks:result:{self.conversation_id}:{task_id}", json.dumps(result))
            r.set(
                f"tasks:node:{self.conversation_id}:{task_id}",
                json.dumps({"state": "completed", "last_status_message": "done"}),
            )
            r.publish(
                f"tasks:events:{self.conversation_id}",
                json.dumps({"type": "state_change", "task_id": task_id, "root_task_id": task_id, "state": "completed"}),
            )
            r.close()
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"    (synthetic publish failed: {exc})")
            return False

    def step_upload(self) -> None:
        files = {"file": ("smoke.txt", b"prometheus smoke upload\n", "text/plain")}
        try:
            r = self.client.post("/api/uploads", files=files, timeout=self.args.turn_timeout)
        except Exception as exc:  # noqa: BLE001
            self.results.record("uploads", FAIL, f"request error: {exc}")
            return
        if r.status_code != 200:
            # 502 = staging failed upstream; the endpoint itself worked.
            level = WARN if r.status_code == 502 else FAIL
            self.results.record("uploads", level, f"HTTP {r.status_code}: {r.text[:120]}")
            return
        desc = r.json()
        upload_id = desc.get("upload_id")
        if not upload_id:
            self.results.record("uploads", FAIL, "descriptor missing upload_id")
            return
        self.results.record("uploads", PASS, f"upload_id={upload_id} size={desc.get('size_bytes')}")
        # Reference the upload in a chat message (echoed back to the agent).
        self._run_turn(
            "chat (with upload)",
            expected={"completed", "answer", "recommendation", "needs_info", "plan_ready", "executing"},
            query=self.args.simple_query,
            upload_ids=[desc],
        )

    def step_artifact_content(self) -> None:
        artifact = next(
            (a for a in self.completed_artifacts if a.get("artifact_id")),
            None,
        )
        if not artifact:
            self.results.record("artifacts/content", SKIP, "no artifact from completed turn to fetch")
            return
        artifact_id = artifact["artifact_id"]
        try:
            r = self.client.get(f"/api/artifacts/{artifact_id}/content", timeout=self.args.turn_timeout)
        except Exception as exc:  # noqa: BLE001
            self.results.record("artifacts/content", FAIL, f"request error: {exc}")
            return
        if r.status_code != 200:
            level = WARN if r.status_code in (404, 502) else FAIL
            self.results.record("artifacts/content", level, f"HTTP {r.status_code}")
            return
        ctype = r.headers.get("content-type", "?")
        self.results.record("artifacts/content", PASS, f"{len(r.content)} bytes, content-type={ctype}")

    def step_history(self) -> None:
        r = self.client.get("/api/conversations/recent")
        if r.status_code != 200:
            self.results.record("conversations/recent", FAIL, f"HTTP {r.status_code}")
            return
        body = r.json()
        if not body.get("available"):
            self.results.record("conversations/recent", WARN, "Redis history unavailable (degraded to empty list)")
            return
        self.results.record("conversations/recent", PASS, f"{len(body.get('conversations', []))} row(s)")

    # -- driver -------------------------------------------------------------- #

    def run(self) -> int:
        print(f"Smoke test against {self.args.base_url}\n")
        try:
            if not self.step_health():
                return self.results.summary_exit_code()
            if not (self.step_login() and self.step_me()):
                return self.results.summary_exit_code()
            self.step_config()
            if not self.step_session():
                return self.results.summary_exit_code()
            if not self.step_open_sse():
                return self.results.summary_exit_code()
            self.step_simple_turn()
            self.step_needs_info()
            self.step_plan()
            self.step_backgrounded()
            self.step_upload()
            self.step_artifact_content()
            self.step_history()
        finally:
            if self.sse:
                self.sse.stop()
            self.client.close()
        return self.results.summary_exit_code()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=_env("SMOKE_BASE_URL", "http://localhost:8600"))
    p.add_argument("--username", default=_env("SMOKE_USERNAME", "prometheus"))
    p.add_argument("--password", default=_env("SMOKE_PASSWORD", "prometheus"))
    p.add_argument("--redis-url", default=_env("SMOKE_REDIS_URL", "redis://localhost:6379"))
    p.add_argument(
        "--synthetic-background",
        action="store_true",
        default=os.environ.get("SMOKE_SYNTHETIC_BACKGROUND", "").lower() in ("1", "true", "yes"),
        help="force deterministic backgrounded-task completion via Redis events",
    )
    p.add_argument("--no-verify", dest="verify", action="store_false", help="disable TLS cert verification")
    # Agent-dependent trigger queries.
    p.add_argument("--simple-query", default=_env("SMOKE_SIMPLE_QUERY", "What is the melting point of SS316?"))
    p.add_argument("--needs-info-query", default=_env("SMOKE_NEEDS_INFO_QUERY", "Design a nuclear system"))
    p.add_argument(
        "--plan-query",
        default=_env(
            "SMOKE_PLAN_QUERY",
            "Create a single-loop PWR primary coolant system with an RPV, SG, and a Pump connected in a closed loop.",
        ),
    )
    p.add_argument("--background-query", default=_env("SMOKE_BACKGROUND_QUERY", "Run FTL Safety Analysis"))
    # Timeouts (seconds).
    p.add_argument("--http-timeout", type=float, default=30.0)
    p.add_argument("--turn-timeout", type=float, default=300.0)
    p.add_argument("--sse-open-timeout", type=float, default=10.0)
    p.add_argument("--sse-frame-timeout", type=float, default=10.0)
    p.add_argument("--background-timeout", type=float, default=60.0)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return Harness(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
