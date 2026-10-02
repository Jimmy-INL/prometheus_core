"""Tool-calling orchestration loop: chaining, pauses, resumption, transcript validity."""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence

import pytest

import runtime_stub  # noqa: F401  (installs prometheus_api.agent stubs)

from prometheus_api.llm_client import ChatResponse, parse_finish_reason, parse_tool_calls

from capability_cache import AgentCapability
from orchestrator import agent_loop, chat_flow, runtime
from orchestrator.models import ConversationRequest

CONV = "conv-loop"


def _capability(skill_id: str, input_schema: Dict[str, Any], **kwargs: Any) -> AgentCapability:
    return AgentCapability(
        agent_id="test-agent",
        agent_name="Test Agent",
        agent_url="http://litellm:4000/a2a/test-agent",
        skill_id=skill_id,
        skill_name=skill_id.replace("_", " ").title(),
        description=f"{skill_id} skill",
        input_schema=input_schema,
        **kwargs,
    )


CREATE_SVG = _capability(
    "create_svg_artifact",
    {
        "type": "object",
        "properties": {
            "word": {"type": "string"},
            "color": {"type": "string"},
            "background_color": {"type": "string"},
        },
        "required": ["word"],
    },
)
CONVERT_PNG = _capability(
    "convert_svg_to_png",
    {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "description": "SVG to convert.", "x_artifact_ref": "single"},
            "artifacts": {"type": "array"},
        },
        "required": ["artifact_id"],
    },
)
THERMAL = _capability(
    "analyze_thermal",
    {
        "type": "object",
        "properties": {
            "material_id": {"type": "string"},
            "temperature_c": {"type": "number", "description": "Operating temperature."},
        },
        "required": ["material_id", "temperature_c"],
    },
)
REVIEW = _capability(
    "review_document",
    {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
    requires_approval=True,
)
CAPABILITIES = [CREATE_SVG, CONVERT_PNG, THERMAL, REVIEW]


def tool_call(name: str, arguments: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def reply(text: str = "", calls: List[Dict[str, Any]] = ()) -> Dict[str, Any]:
    message: Dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = list(calls)
    # Some providers report "stop" alongside tool calls; the loop must not care.
    return {"choices": [{"message": message, "finish_reason": "stop"}]}


class ScriptedLLM:
    """Stands in for ``runtime.create_llm()``; each ``medium`` call pops one step."""

    def __init__(self, script: List[Any]):
        self.script = list(script)
        self.requests: List[Dict[str, Any]] = []
        self.medium_clients: List[int] = []  # which created client served each medium call
        self._created = 0

    def __call__(self, *args: Any, **kwargs: Any) -> "_ScriptedClient":
        self._created += 1
        return _ScriptedClient(self, self._created)

    async def medium(self, client: int, messages: List[Dict[str, Any]], **kwargs: Any) -> ChatResponse:
        assert kwargs.get("tool_choice") == "auto"
        self.medium_clients.append(client)
        request = {
            "messages": copy.deepcopy(messages),
            "tools": {tool.name: tool for tool in kwargs.get("tools", [])},
        }
        self.requests.append(request)
        step = self.script.pop(0)
        raw = step(request) if callable(step) else step
        return ChatResponse(
            text=raw["choices"][0]["message"].get("content") or "",
            model_alias="medium",
            provider_model=None,
            usage=None,
            raw=raw,
            tool_calls=parse_tool_calls(raw),
            finish_reason=parse_finish_reason(raw),
        )


class _ScriptedClient:
    def __init__(self, llm: ScriptedLLM, index: int):
        self.llm = llm
        self.index = index

    async def __aenter__(self) -> "_ScriptedClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def medium(self, messages: List[Dict[str, Any]], **kwargs: Any) -> ChatResponse:
        return await self.llm.medium(self.index, messages, **kwargs)

    async def small(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(text="Test title")


@pytest.fixture
def harness(monkeypatch):
    store: Dict[str, Any] = {}
    invocations: List[tuple] = []
    results: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
    capabilities = list(CAPABILITIES)
    llms: List[ScriptedLLM] = []

    def save(conv_id: str, state: Dict[str, Any]) -> None:
        # Round-trip through JSON: persisted state must be serializable.
        store[conv_id] = json.loads(json.dumps(state))

    async def get_capabilities():
        return capabilities

    async def fake_invoke(skill_id, params, conversation_id, emit_status=True):
        invocations.append((skill_id, copy.deepcopy(params)))
        outcome = results[skill_id](params)  # may raise, like a broken transport
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return {"skill_id": skill_id, **outcome}

    monkeypatch.setattr(chat_flow, "get_conversation", lambda conv_id: copy.deepcopy(store.get(conv_id)))
    monkeypatch.setattr(chat_flow, "store_conversation", save)
    monkeypatch.setattr(runtime, "store_status_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "ENABLE_WORKFLOW_LIBRARY", False)
    monkeypatch.setattr(
        agent_loop, "get_capability_cache", lambda: SimpleNamespace(get_capabilities=get_capabilities)
    )
    monkeypatch.setattr(agent_loop, "invoke_skill", fake_invoke)

    def script(steps: List[Any]) -> ScriptedLLM:
        llm = ScriptedLLM(steps)
        llms.append(llm)
        monkeypatch.setattr(runtime, "create_llm", llm)
        return llm

    yield SimpleNamespace(
        store=store, invocations=invocations, results=results, capabilities=capabilities, script=script
    )
    for llm in llms:
        assert llm.script == [], f"{len(llm.script)} scripted LLM step(s) never ran"


def send(**kwargs: Any):
    return asyncio.run(chat_flow.chat(ConversationRequest(conversation_id=CONV, **kwargs)))


def assert_transcript_valid(messages: List[Dict[str, Any]]) -> None:
    """Every tool call is answered exactly once, in order, before the next turn."""
    open_ids: List[str] = []
    for message in messages:
        # Only a pure tool-call turn may omit content.
        assert message.get("content") or message.get("tool_calls"), message
        if message["role"] == "tool":
            assert open_ids and message["tool_call_id"] == open_ids.pop(0)
            continue
        assert not open_ids, f"unanswered tool calls before {message['role']}"
        if message["role"] == "assistant":
            open_ids = [call["id"] for call in message.get("tool_calls") or []]
    assert not open_ids


def svg_result(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "result": {
            "status": "success",
            "message": f"SVG artifact created with word {params['word']}.",
            "artifacts": [
                {
                    "artifact_id": "svg-1",
                    "name": "popelnase.svg",
                    "mime_type": "image/svg+xml",
                    "description": "SVG with the word.",
                    "uri": "deeplynx://organizations/1/projects/1/items/1",
                }
            ],
        }
    }


def png_result(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "result": {
            "status": "success",
            "message": "Converted to PNG.",
            "artifacts": [
                {
                    "artifact_id": "png-1",
                    "name": "popelnase.png",
                    "mime_type": "image/png",
                    "uri": "deeplynx://organizations/1/projects/1/items/2",
                }
            ],
        }
    }


# --------------------------------------------------------------------------- #
# Chaining
# --------------------------------------------------------------------------- #


def test_png_request_chains_two_skills_through_produced_artifact(harness) -> None:
    harness.results.update(create_svg_artifact=svg_result, convert_svg_to_png=png_result)

    def second_turn(request):
        tool_message = request["messages"][-1]
        assert tool_message["role"] == "tool"
        assert json.loads(tool_message["content"])["artifacts"][0]["artifact_id"] == "svg-1"
        assert "svg-1: popelnase.svg" in request["messages"][0]["content"]
        return reply(calls=[tool_call("convert_svg_to_png", {"artifact_id": "svg-1"}, "c2")])

    llm = harness.script(
        [
            reply(calls=[tool_call("create_svg_artifact", {"word": "Popelnase"}, "c1")]),
            second_turn,
            reply("Here is popelnase.png."),
        ]
    )

    response = send(query="Create a PNG image with the word Popelnase")

    assert response.status == "completed"
    assert response.report == "Here is popelnase.png."
    assert [skill for skill, _ in harness.invocations] == ["create_svg_artifact", "convert_svg_to_png"]
    png_params = harness.invocations[1][1]
    assert png_params["artifact_id"] == "svg-1"
    assert [a["artifact_id"] for a in png_params["artifacts"]] == ["svg-1"]
    assert set(response.tool_results) == {"create_svg_artifact", "convert_svg_to_png"}
    assert len(llm.requests) == 3
    assert len(set(llm.medium_clients)) == 1  # one client for all three LLM turns

    state = harness.store[CONV]
    assert_transcript_valid(state["llm_messages"])
    assert [a["artifact_id"] for a in state["context"]["artifacts"]] == ["svg-1", "png-1"]
    assert state["final_report"] == "Here is popelnase.png."
    assert state["conversation_history"][-1]["tool_inputs"]["create_svg_artifact"] == {"word": "Popelnase"}


def test_explicit_steps_pass_literal_parameters(harness) -> None:
    harness.results.update(create_svg_artifact=svg_result, convert_svg_to_png=png_result)
    harness.script(
        [
            reply(
                calls=[
                    tool_call(
                        "create_svg_artifact",
                        {"word": "Popelnase", "color": "green", "background_color": "brown"},
                        "c1",
                    )
                ]
            ),
            reply(calls=[tool_call("convert_svg_to_png", {"artifact_id": "svg-1"}, "c2")]),
            reply("Done."),
        ]
    )

    response = send(
        query="Create an image with the word Popelnase in green on a brown background, then convert it to png"
    )

    assert response.status == "completed"
    assert harness.invocations[0][1]["color"] == "green"
    assert harness.invocations[0][1]["background_color"] == "brown"


def test_independent_calls_in_one_turn_all_run_and_answer_in_order(harness) -> None:
    harness.results.update(
        analyze_thermal=lambda params: {"result": {"answer": f"{params['material_id']} ok"}},
    )
    llm = harness.script(
        [
            reply(
                calls=[
                    tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": 500}, "a"),
                    tool_call("analyze_thermal", {"material_id": "SS347", "temperature_c": 500}, "b"),
                ]
            ),
            reply("Both analyzed."),
        ]
    )

    response = send(query="Compare thermal behavior of SS316 and SS347 at 500 C")

    assert response.status == "completed"
    assert sorted(params["material_id"] for _, params in harness.invocations) == ["SS316", "SS347"]
    tool_messages = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["a", "b"]
    assert sorted(
        (key, result["answer"]) for key, result in response.tool_results.items()
    ) == [("analyze_thermal", "SS316 ok"), ("analyze_thermal#2", "SS347 ok")]
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_independent_calls_run_concurrently(harness) -> None:
    barrier = asyncio.Barrier(2)

    async def meet(params):
        # A sequential batch would leave the first call waiting here forever.
        await asyncio.wait_for(barrier.wait(), timeout=2)
        return {"result": {"answer": f"{params['material_id']} ok"}}

    harness.results.update(analyze_thermal=meet)
    harness.script(
        [
            reply(
                calls=[
                    tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": 500}, "a"),
                    tool_call("analyze_thermal", {"material_id": "SS347", "temperature_c": 500}, "b"),
                ]
            ),
            reply("Both analyzed."),
        ]
    )

    assert send(query="Compare SS316 and SS347 at 500 C").status == "completed"


def test_one_failing_call_does_not_sink_its_sibling(harness, caplog) -> None:
    def thermal(params):
        if params["material_id"] == "SS347":
            raise KeyError("transport lost")
        return {"result": {"answer": "SS316 ok"}}

    def sees_both(request):
        results = {m["tool_call_id"]: json.loads(m["content"]) for m in request["messages"] if m["role"] == "tool"}
        assert results["a"]["status"] == "succeeded"
        assert results["b"]["status"] == "failed"
        assert "transport lost" in results["b"]["error"]
        return reply("SS316 is fine; SS347 could not be analyzed.")

    harness.results.update(analyze_thermal=thermal)
    harness.script(
        [
            reply(
                calls=[
                    tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": 500}, "a"),
                    tool_call("analyze_thermal", {"material_id": "SS347", "temperature_c": 500}, "b"),
                ]
            ),
            sees_both,
        ]
    )

    with caplog.at_level(logging.ERROR, logger="orchestrator.agent_loop"):
        response = send(query="Compare SS316 and SS347 at 500 C")

    assert response.status == "completed"
    assert response.tool_results == {"analyze_thermal": {"answer": "SS316 ok"}}
    failures = [r for r in caplog.records if r.name == "orchestrator.agent_loop" and r.levelno == logging.ERROR]
    assert len(failures) == 1 and failures[0].exc_info is not None
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_repeated_skill_keeps_every_result_in_the_turn(harness) -> None:
    outcomes = iter([{"result": {"answer": "SS316 ok"}}, {"error": "agent unavailable"}])
    harness.results.update(analyze_thermal=lambda params: next(outcomes))
    harness.script(
        [
            reply(calls=[tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": 500}, "a")]),
            reply(calls=[tool_call("analyze_thermal", {"material_id": "SS347", "temperature_c": 500}, "b")]),
            reply("SS316 is fine; SS347 failed."),
        ]
    )

    response = send(query="Analyze SS316, then SS347")

    assert response.tool_results == {
        "analyze_thermal": {"answer": "SS316 ok"},
        "analyze_thermal#2": {"error": "agent unavailable"},
    }


def test_call_without_a_provider_id_keeps_its_result(harness) -> None:
    harness.results.update(create_svg_artifact=svg_result)

    def sees_result(request):
        assistant = next(m for m in request["messages"] if m.get("tool_calls"))
        call_id = assistant["tool_calls"][0]["id"]
        assert call_id
        tool_message = request["messages"][-1]
        assert tool_message["tool_call_id"] == call_id
        assert json.loads(tool_message["content"])["status"] == "succeeded"
        return reply("Created the SVG.")

    harness.script([reply(calls=[tool_call("create_svg_artifact", {"word": "x"}, "")]), sees_result])

    assert send(query="Make an SVG").status == "completed"
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_conversational_message_answers_without_skills(harness) -> None:
    harness.script([reply("Hello! How can I help?")])

    response = send(query="hi")

    assert response.status == "answer"
    assert response.response_text == "Hello! How can I help?"
    assert harness.invocations == []


# --------------------------------------------------------------------------- #
# Validation feedback to the model
# --------------------------------------------------------------------------- #


def test_unknown_artifact_reference_is_returned_to_the_model(harness) -> None:
    def sees_error(request):
        content = json.loads(request["messages"][-1]["content"])
        assert content["status"] == "failed"
        assert "Unknown artifact_id nope" in content["error"]
        return reply("There is no SVG to convert yet.")

    harness.script([reply(calls=[tool_call("convert_svg_to_png", {"artifact_id": "nope"}, "c1")]), sees_error])

    response = send(query="Convert my SVG to PNG")

    assert response.status == "answer"
    assert harness.invocations == []


def test_schema_violation_is_returned_to_the_model(harness) -> None:
    def sees_error(request):
        content = json.loads(request["messages"][-1]["content"])
        assert "temperature_c" in content["error"]
        return reply("Please give a numeric temperature.")

    harness.script(
        [
            reply(calls=[tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": "hot"}, "c1")]),
            sees_error,
        ]
    )

    assert send(query="Analyze SS316 when hot").status == "answer"
    assert harness.invocations == []


def test_missing_runtime_input_sends_the_model_upstream_instead_of_asking(harness) -> None:
    harness.capabilities.append(
        _capability(
            "generate_mesh",
            {
                "type": "object",
                "properties": {
                    "geometry_id": {"type": "string", "x_input_source": "runtime"},
                    "element_size": {"type": "number"},
                },
                "required": ["geometry_id", "element_size"],
            },
        )
    )

    def sees_error(request):
        content = json.loads(request["messages"][-1]["content"])
        assert content["status"] == "failed"
        assert "geometry_id" in content["error"]
        assert "call the upstream skill first" in content["error"]
        return reply("I need a geometry first.")

    harness.script([reply(calls=[tool_call("generate_mesh", {"element_size": 0.5}, "c1")]), sees_error])

    response = send(query="Mesh it at 0.5")

    assert response.status == "answer"
    assert not response.followup_questions
    assert harness.invocations == []


def test_unknown_tool_and_bad_json_are_returned_to_the_model(harness) -> None:
    def sees_errors(request):
        first, second = [json.loads(m["content"]) for m in request["messages"] if m["role"] == "tool"]
        assert "Unknown tool" in first["error"]
        assert "not valid JSON" in second["error"]
        return reply("Sorry.")

    bad_json = {"id": "c2", "type": "function", "function": {"name": "create_svg_artifact", "arguments": "{oops"}}
    harness.script([reply(calls=[tool_call("teleport", {}, "c1"), bad_json]), sees_errors])

    assert send(query="do things").status == "answer"


# --------------------------------------------------------------------------- #
# Pauses and resumption
# --------------------------------------------------------------------------- #


def test_missing_user_input_pauses_for_a_typed_form_then_runs(harness) -> None:
    harness.results.update(analyze_thermal=lambda params: {"result": {"answer": "Fatigue margin OK."}})
    llm = harness.script(
        [
            reply("I need the operating temperature.", [tool_call("analyze_thermal", {"material_id": "SS316"}, "c1")]),
            reply("Fatigue margin is OK at 550 C."),
        ]
    )

    first = send(query="Analyze thermal fatigue for SS316")

    assert first.status == "needs_info"
    assert first.message == "I need the operating temperature."
    assert [(q["field"], q["type"]) for q in first.followup_questions] == [("temperature_c", "number")]
    assert harness.invocations == []
    assert harness.store[CONV]["missing_info"] == ["temperature_c"]

    second = send(followup_answers={"temperature_c": "550"})

    assert second.status == "completed"
    assert harness.invocations[0][1]["temperature_c"] == 550.0
    assert len(llm.requests) == 2
    assert_transcript_valid(harness.store[CONV]["llm_messages"])
    assert harness.store[CONV]["missing_info"] == []


def test_unparseable_number_asks_again(harness) -> None:
    harness.script([reply(calls=[tool_call("analyze_thermal", {"material_id": "SS316"}, "c1")])])

    send(query="Analyze thermal fatigue for SS316")
    response = send(followup_answers={"temperature_c": "ten"})

    assert response.status == "needs_info"
    assert [q["field"] for q in response.followup_questions] == ["temperature_c"]
    assert harness.invocations == []


def test_coerce_answer_treats_unparseable_values_as_absent() -> None:
    assert agent_loop.coerce_answer("550", "number") == 550.0
    assert agent_loop.coerce_answer("ten", "number") is None
    assert agent_loop.coerce_answer("2.5", "integer") is None
    assert agent_loop.coerce_answer("3", "integer") == 3


def test_resume_sends_a_bounded_transcript(harness) -> None:
    harness.results.update(analyze_thermal=lambda params: {"result": {"answer": "OK."}})
    llm = harness.script(
        [reply(calls=[tool_call("analyze_thermal", {"material_id": "SS316"}, "c1")]), reply("OK at 550 C.")]
    )
    send(query="Analyze SS316")
    # Earlier turns pile up in storage (other turns' messages merge back in).
    old_turns = [
        message
        for index in range(60)
        for message in ({"role": "user", "content": f"q{index}"}, {"role": "assistant", "content": f"a{index}"})
    ]
    harness.store[CONV]["llm_messages"] = old_turns + harness.store[CONV]["llm_messages"]

    assert send(followup_answers={"temperature_c": "550"}).status == "completed"

    sent = llm.requests[-1]["messages"]
    assert len(sent) <= agent_loop.MAX_TRANSCRIPT_MESSAGES + 1  # plus the system prompt
    assert sent[1]["role"] == "user"
    assert_transcript_valid(sent[1:])


def test_approval_required_skill_waits_for_approval(harness) -> None:
    harness.results.update(review_document=lambda params: {"result": {"answer": "Reviewed."}})
    harness.script([reply(calls=[tool_call("review_document", {"title": "SAR"}, "c1")]), reply("Review complete.")])

    first = send(query="Review the SAR")

    assert first.status == "plan_ready"
    assert first.plan["skills"] == ["review_document"]
    assert first.plan["steps"][0]["description"] == 'review_document(title="SAR")'
    assert harness.store[CONV]["awaiting_approval"] is True
    assert harness.invocations == []

    second = send(plan_approved=True)

    assert second.status == "completed"
    assert [skill for skill, _ in harness.invocations] == ["review_document"]
    assert harness.store[CONV]["awaiting_approval"] is False


def test_rejected_plan_closes_the_calls_without_running_them(harness) -> None:
    llm = harness.script([reply(calls=[tool_call("review_document", {"title": "SAR"}, "c1")])])

    send(query="Review the SAR")
    response = send(plan_rejected=True)

    assert response.status == "answer"
    assert harness.invocations == []
    state = harness.store[CONV]
    assert state["pending_calls"] == []
    assert json.loads(state["llm_messages"][-1]["content"])["status"] == "rejected"
    assert_transcript_valid(state["llm_messages"])
    assert len(llm.requests) == 1


def test_free_text_while_awaiting_approval_supersedes_the_calls(harness) -> None:
    def sees_reply(request):
        content = json.loads(request["messages"][-1]["content"])
        assert content["status"] == "not_executed"
        assert "use the draft instead" in content["message"]
        return reply("Understood, I'll wait for the draft.")

    harness.script([reply(calls=[tool_call("review_document", {"title": "SAR"}, "c1")]), sees_reply])

    send(query="Review the SAR")
    response = send(query="use the draft instead")

    assert response.status == "answer"
    assert harness.invocations == []
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_specialist_input_required_resumes_the_same_task(harness) -> None:
    replies = iter(
        [
            {
                "input_required": {
                    "missing_inputs": [{"name": "units", "type": "string", "user_prompt": "Which units?"}],
                    "hint": "The thermal agent needs the unit system.",
                },
                "_a2a_context_id": "ctx-1",
                "_a2a_task_id": "task-1",
                "_task_graph_node_id": "node-1",
            },
            {"result": {"answer": "Done in SI."}},
        ]
    )
    harness.results.update(analyze_thermal=lambda params: next(replies))
    harness.script(
        [
            reply(calls=[tool_call("analyze_thermal", {"material_id": "SS316", "temperature_c": 500}, "c1")]),
            reply("Analysis complete."),
        ]
    )

    first = send(query="Analyze SS316 at 500 C")

    assert first.status == "needs_info"
    assert first.message == "The thermal agent needs the unit system."
    assert first.followup_questions[0]["field"] == "units"

    second = send(followup_answers={"units": "SI"})

    assert second.status == "completed"
    resume_params = harness.invocations[1][1]
    assert resume_params["provided_inputs"] == {"units": "SI"}
    assert resume_params["_a2a_task_id"] == "task-1"
    assert resume_params["_a2a_context_id"] == "ctx-1"
    assert resume_params["_task_graph_node_id"] == "node-1"
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_ask_user_accepts_a_free_text_answer(harness) -> None:
    def sees_answer(request):
        assert json.loads(request["messages"][-1]["content"]) == {"status": "answered", "reply": "Option B"}
        return reply("Going with option B.")

    harness.script(
        [
            reply(
                calls=[
                    tool_call(
                        "ask_user",
                        {"questions": [{"field": "approach", "question": "A or B?", "options": ["A", "B"]}]},
                        "c1",
                    )
                ]
            ),
            sees_answer,
        ]
    )

    first = send(query="Pick an approach for me")
    assert first.status == "needs_info"
    assert first.followup_questions == [
        {"field": "approach", "question": "A or B?", "type": "select", "options": ["A", "B"]}
    ]

    assert send(query="Option B").status == "answer"


def test_turn_limit_ends_with_an_error_and_a_valid_transcript(harness, monkeypatch) -> None:
    monkeypatch.setattr(agent_loop, "MAX_LLM_TURNS", 2)
    harness.results.update(create_svg_artifact=svg_result)
    harness.script(
        [reply(calls=[tool_call("create_svg_artifact", {"word": "x"}, f"c{i}")]) for i in range(2)]
    )

    response = send(query="loop forever")

    assert response.status == "error"
    assert "Stopped after 2" in response.message
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_next_user_turn_sees_previous_results(harness) -> None:
    harness.results.update(create_svg_artifact=svg_result)
    llm = harness.script(
        [
            reply(calls=[tool_call("create_svg_artifact", {"word": "Popelnase"}, "c1")]),
            reply("Created the SVG."),
            reply("It contains the word Popelnase."),
        ]
    )

    send(query="Make an SVG with Popelnase")
    response = send(query="What word is in it?")

    assert response.status == "answer"
    history = llm.requests[2]["messages"]
    assert history[-1] == {"role": "user", "content": "What word is in it?"}
    assert any(m["role"] == "tool" and "svg-1" in m["content"] for m in history)


# --------------------------------------------------------------------------- #
# Tool catalog
# --------------------------------------------------------------------------- #


def test_empty_final_answer_is_an_error_not_a_broken_transcript(harness) -> None:
    harness.script([reply("")])

    response = send(query="hi")

    assert response.status == "error"
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_catalog_advertises_plain_schemas(harness) -> None:
    catalog = asyncio.run(agent_loop.build_tool_catalog())

    convert = catalog["convert_svg_to_png"]
    properties = convert.parameters["properties"]
    assert set(properties) == {"artifact_id"}
    assert "x_artifact_ref" not in properties["artifact_id"]
    assert "artifact_id of an existing conversation artifact" in properties["artifact_id"]["description"]
    assert convert.parameters["required"] == ["artifact_id"]
    assert "Requires user approval" in catalog["review_document"].description
    assert agent_loop.ASK_USER_TOOL in catalog


WORKFLOW_ID = "thermal.quick_check"


def _workflow(version: str) -> SimpleNamespace:
    definition = SimpleNamespace(
        id=WORKFLOW_ID,
        version=version,
        name="Quick Thermal Check",
        description="Thermal screening.",
        steps=[SimpleNamespace(id="s1", skill_id="analyze_thermal")],
        metadata=SimpleNamespace(requires_approval=False, estimated_duration_seconds=60),
        ui=SimpleNamespace(display_name="Quick Thermal Check"),
    )
    return SimpleNamespace(definition=definition, required_input_paths=["material_id"])


def _screened(**extra: Any) -> Dict[str, Any]:
    return {
        "step_statuses": {"s1": "succeeded"},
        "step_results": {"s1": {"skill_id": "analyze_thermal", "result": {"answer": "Screened."}}},
        "final_output": {"answer": "Screened."},
        "input_required_steps": [],
        "errors": [],
        **extra,
    }


def _install_workflow(
    monkeypatch,
    *,
    versions: Sequence[str] = ("1.0.0",),
    execute: Optional[Callable[..., Any]] = None,
    health_error: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Install a one-step workflow registry; returns the recorded execute_workflow calls."""
    workflows = {version: _workflow(version) for version in versions}
    newest = workflows[versions[-1]]
    form_field = {"field": "material_id", "label": "Material", "description": "Material id", "type": "string"}
    registry = SimpleNamespace(
        list_all=lambda: [newest],
        get=lambda workflow_id, version=None: workflows.get(version) if version else newest,
        build_input_form=lambda **kwargs: {"fields": [form_field]},
    )
    executed: List[Dict[str, Any]] = []

    async def fake_execute_workflow(workflow, input_params, context, invoke_skill, conversation_id):
        executed.append({"version": workflow.definition.version, "inputs": copy.deepcopy(input_params)})
        if execute is None:
            return _screened()
        outcome = execute(context)
        return await outcome if inspect.isawaitable(outcome) else outcome

    async def health(workflow):
        return health_error

    monkeypatch.setattr(runtime, "ENABLE_WORKFLOW_LIBRARY", True)
    monkeypatch.setattr(agent_loop, "get_workflow_registry", lambda: registry)
    monkeypatch.setattr(agent_loop, "execute_workflow", fake_execute_workflow)
    monkeypatch.setattr(agent_loop, "verify_workflow_source_health", health)
    return executed


def test_explicit_workflow_start_collects_inputs_then_runs(harness, monkeypatch) -> None:
    executed = _install_workflow(monkeypatch)
    llm = harness.script([reply("Screening passed.")])

    first = send(workflow_id=WORKFLOW_ID)

    assert first.status == "needs_info"
    assert first.followup_questions[0]["field"] == "material_id"
    assert llm.requests == []

    second = send(followup_answers={"material_id": "SS316"})

    assert second.status == "completed"
    assert executed[0]["inputs"]["material_id"] == "SS316"
    assert "analyze_thermal" in second.tool_results
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_explicit_workflow_start_runs_the_requested_version(harness, monkeypatch) -> None:
    executed = _install_workflow(monkeypatch, versions=("1.0.0", "2.0.0"))
    harness.script([reply("Screening passed.")])

    response = send(workflow_id=WORKFLOW_ID, workflow_version="1.0.0", followup_answers={"material_id": "SS316"})

    assert response.status == "completed"
    assert [run["version"] for run in executed] == ["1.0.0"]


def test_unhealthy_workflow_source_fails_the_call_without_running(harness, monkeypatch) -> None:
    executed = _install_workflow(monkeypatch, health_error="Workflow source repo is unreachable.")

    def sees_error(request):
        content = json.loads(request["messages"][-1]["content"])
        assert content == {"status": "failed", "error": "Workflow source repo is unreachable."}
        return reply("The workflow source is down right now.")

    harness.script([sees_error])

    response = send(workflow_id=WORKFLOW_ID, followup_answers={"material_id": "SS316"})

    assert response.status == "answer"
    assert executed == []


def test_workflow_input_required_resumes_each_blocked_step(harness, monkeypatch) -> None:
    runs = iter(
        [
            _screened(
                step_statuses={"s1": "input_required", "s2": "input_required"},
                step_results={},
                input_required_steps=[
                    {
                        "skill_id": "analyze_thermal",
                        "input_required": {"missing_inputs": [{"name": "units", "type": "string"}], "hint": "Units?"},
                        "_a2a_task_id": "task-thermal",
                        "_a2a_context_id": "ctx-thermal",
                    },
                    {
                        "skill_id": "create_svg_artifact",
                        "input_required": {"missing_inputs": [{"name": "color", "type": "string"}]},
                        "_a2a_task_id": "task-svg",
                    },
                ],
            ),
            _screened(),
        ]
    )
    executed = _install_workflow(monkeypatch, execute=lambda context: next(runs))
    svg_replies = iter(
        [
            {
                "input_required": {"missing_inputs": [{"name": "word", "type": "string"}]},
                "_a2a_task_id": "task-svg-2",
            },
            svg_result({"word": "x"}),
        ]
    )
    harness.results.update(
        analyze_thermal=lambda params: {"result": {"answer": "SI it is."}},
        create_svg_artifact=lambda params: next(svg_replies),
    )
    harness.script([reply("Screening passed.")])

    first = send(workflow_id=WORKFLOW_ID, followup_answers={"material_id": "SS316"})
    assert first.status == "needs_info"
    assert first.message == "Units?"
    assert sorted(q["field"] for q in first.followup_questions) == ["color", "units"]

    second = send(followup_answers={"units": "SI", "color": "red"})
    # Each blocked task gets only its own inputs, on its own A2A task.
    resumed = {skill: params for skill, params in harness.invocations}
    assert resumed["analyze_thermal"]["provided_inputs"] == {"units": "SI"}
    assert resumed["analyze_thermal"]["_a2a_task_id"] == "task-thermal"
    assert resumed["analyze_thermal"]["_a2a_context_id"] == "ctx-thermal"
    assert resumed["create_svg_artifact"]["provided_inputs"] == {"color": "red"}
    assert resumed["create_svg_artifact"]["_a2a_task_id"] == "task-svg"
    # The SVG step is still blocked, so the template does not re-run yet.
    assert second.status == "needs_info"
    assert [q["field"] for q in second.followup_questions] == ["word"]
    assert len(executed) == 1

    third = send(followup_answers={"word": "x"})

    last_skill, last_params = harness.invocations[-1]
    assert (last_skill, last_params["provided_inputs"]) == ("create_svg_artifact", {"word": "x"})
    assert last_params["_a2a_task_id"] == "task-svg-2"
    assert third.status == "completed"
    assert len(executed) == 2
    assert {"material_id": "SS316", "units": "SI", "color": "red", "word": "x"}.items() <= executed[1]["inputs"].items()
    assert_transcript_valid(harness.store[CONV]["llm_messages"])


def test_workflow_keeps_artifacts_a_sibling_call_produced_meanwhile(harness, monkeypatch) -> None:
    async def slow_screen(context):
        for _ in range(5):  # let the sibling SVG call finish while this "runs"
            await asyncio.sleep(0)
        return _screened()

    _install_workflow(monkeypatch, execute=slow_screen)
    harness.results.update(create_svg_artifact=svg_result, convert_svg_to_png=png_result)
    workflow_tool = agent_loop.workflow_tool_for(asyncio.run(agent_loop.build_tool_catalog()), WORKFLOW_ID)
    harness.script(
        [
            reply(
                calls=[
                    tool_call(workflow_tool.name, {"material_id": "SS316"}, "w1"),
                    tool_call("create_svg_artifact", {"word": "x"}, "c1"),
                ]
            ),
            reply(calls=[tool_call("convert_svg_to_png", {"artifact_id": "svg-1"}, "c2")]),
            reply("Screened and converted."),
        ]
    )

    response = send(query="Screen SS316 and make an SVG, then convert it")

    assert response.status == "completed"
    assert [skill for skill, _ in harness.invocations] == ["create_svg_artifact", "convert_svg_to_png"]
    artifacts = [a["artifact_id"] for a in harness.store[CONV]["context"]["artifacts"]]
    assert artifacts == ["svg-1", "png-1"]


# --------------------------------------------------------------------------- #
# Concurrent turns: transcript repair and restore fidelity
# --------------------------------------------------------------------------- #


def test_llm_view_repairs_a_transcript_interleaved_by_another_turn() -> None:
    call = tool_call("analyze_thermal", {"material_id": "SS316"}, "c1")
    other = tool_call("create_svg_artifact", {"word": "x"}, "c9")
    messages = [
        {"role": "user", "content": "analyze", "turn_id": "A", "turn_started_at": 1.0},
        {"role": "assistant", "content": None, "tool_calls": [call], "turn_id": "A", "turn_started_at": 1.0},
        # Turn B ran in between, and its own pending call was superseded.
        {"role": "user", "content": "other", "turn_id": "B", "turn_started_at": 2.0},
        {"role": "assistant", "content": None, "tool_calls": [other], "turn_id": "B", "turn_started_at": 2.0},
        # A resumed in turn C: its result now sits after B's block.
        {"role": "tool", "tool_call_id": "c1", "content": "{\"status\": \"succeeded\"}", "turn_id": "C"},
        {"role": "tool", "tool_call_id": "orphan", "content": "{}", "turn_id": "C"},
    ]

    view = agent_loop.llm_view(messages)

    assert [(m["role"], m.get("tool_call_id")) for m in view] == [
        ("user", None),
        ("assistant", None),
        ("tool", "c1"),
        ("user", None),
        ("assistant", None),
        ("tool", "c9"),
    ]
    assert json.loads(view[5]["content"])["status"] == "not_executed"
    assert all("turn_id" not in m and "turn_started_at" not in m for m in view)
    assert_transcript_valid(view)


def test_pause_entries_carry_the_reply_text_and_approval_adds_no_bubble(harness) -> None:
    harness.results.update(review_document=lambda params: {"result": {"answer": "Reviewed."}})
    harness.script(
        [reply("Shall I review it?", [tool_call("review_document", {"title": "SAR"}, "c1")]), reply("Done.")]
    )

    send(query="Review the SAR")
    plan_entry = harness.store[CONV]["conversation_history"][-1]
    assert plan_entry["type"] == "plan" and plan_entry["content"] == "Shall I review it?"

    send(plan_approved=True)
    approval = next(e for e in harness.store[CONV]["conversation_history"] if e.get("type") == "plan_approved")
    assert "content" not in approval
