# Testing your agent

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

Test without a platform (deck 04, slide 20 and A21): plain functions for the logic, mocks for
`_execute`, never a real LLM. `uv run pytest` and `uv run ruff check .` must pass (ruff: `E`,
`F`, `I`; `uv run ruff check . --fix` sorts imports).

## Set up the host once

In the agent folder: `uv sync`, then `uv pip install "git+https://github.inl.gov/genesis/prometheus_api.git@<pin>"`
(or `git+ssh://git@github.inl.gov/...`). The template does not list `prometheus_api`, so without
it the tests fail with `ModuleNotFoundError: No module named 'prometheus_api'`. A later bare
`uv sync` removes it again: use `uv sync --inexact`. Add a dependency with
`uv add --no-sync <pkg>`, then `uv sync --inexact`; commit `uv.lock` with `pyproject.toml`.

## Fixtures and mocks

`tests/conftest.py` gives `context` (`context_id = "test-conversation"`) and `event_queue` (an
`AsyncMock`; check `event_queue.enqueue_event.await_count`). `asyncio_mode = "auto"`. Pass
`skill_id` in `params` yourself: the base class sets it from the metadata only in production
(`prometheus_api/prometheus_api/agent/base.py:462-469`). Write one test per skill, and one for an
unknown `skill_id`.

| your code calls | in a test |
|---|---|
| `get_artifact_file_path` | `monkeypatch.setattr(agent, "get_artifact_file_path", fake)`, where `async def fake(artifact_id, **kw): return TESTS_DIR / "fixtures/x.md"` |
| `send_json_artifact`, `send_status_update` | leave them: they emit on the mocked `event_queue` |
| `send_deeplynx_artifact` | `AsyncMock(return_value=SimpleNamespace(artifact_id="png-1", uri="deeplynx://test"))` |
| `ConnectionConfig.from_env()`, `LLMConfig.from_env()` | patch them on `agent.` when the `.env` points to container paths |
| `self.llm_client(...)` | a fake with `__aenter__`/`__aexit__` and `chat()`/`medium()` that return `ChatResponse(text=..., tool_calls=...)` |
| `load_prompt(...)` | pass `prompts_dir=Path(__file__).with_name("prompts")` (`prometheus_api/prometheus_api/prompts.py:11-35`) |

## Mock the LLM

Patch `monkeypatch.setattr(agent, "llm_client", lambda context, **kw: fake)`. For `acall_tool`,
give the fake `tool_calls=[ToolCall(id="c1", name="pick", arguments={...})]`
(`prometheus_api/prometheus_api/llm_client/tools.py:34-46`). For input-required, patch
`load_context_state`, `save_context_state`, and `get_provided_inputs`, and call `_execute` twice
on the same agent: the first returns `{}`, the second the result (`asking-the-user.md`). Tests do
not prove routing: after they pass, `make up` and test in a fresh chat.
