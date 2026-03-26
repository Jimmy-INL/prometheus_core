import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chainlit as cl
import httpx

import plugins as _plugins
from utils.a2a_client import A2AClient, ConversationResponse
from utils.settings import settings


def _format_status_history(history: List[str]) -> str:
    if not history:
        return ""
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(history, start=1))


async def _update_status_step(step: cl.Step, history: List[str], message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    if not history or history[-1] != text:
        history.append(text)
    step.name = text
    step.output = _format_status_history(history)
    await step.update()


def _get_a2a_client() -> A2AClient:
    return A2AClient(
        agent_url=settings.agent_url,
        agent_secret=settings.agent_secret,
    )


async def message_handler(message: cl.Message):
    # --- File upload handling ---
    if message.elements:
        for element in message.elements:
            if not element.name:
                continue

            file_path = Path(element.path)

            # Try visualization plugins first
            plugin = _plugins.find_plugin_for_upload(file_path)
            if plugin is not None:
                try:
                    await cl.Message(content=f"Processing **{element.name}**…").send()
                    description, viewer_elements = await _plugins.process_upload(file_path)
                    await cl.Message(content=description, elements=viewer_elements).send()
                except Exception as e:
                    await cl.Message(
                        content=f"Failed to process **{element.name}**: {e}"
                    ).send()
                if not message.content.strip():
                    return
                continue

            # Fallback: PDF (Chainlit native element)
            if file_path.suffix.lower() == ".pdf":
                try:
                    pdf_el = cl.Pdf(name=element.name, display="inline", path=element.path)
                    await cl.Message(
                        content=f"**PDF loaded:** {element.name}", elements=[pdf_el]
                    ).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to display PDF: {e}").send()
                if not message.content.strip():
                    return

    # --- Text query → A2A client-agent ---
    conversation_id = cl.user_session.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        cl.user_session.set("conversation_id", conversation_id)

    artifacts_catalog = cl.user_session.get("artifacts", [])
    client = _get_a2a_client()

    status_history: List[str] = []
    status_step = cl.Step(name="Sending request to agent...", type="tool")

    async def _on_status(msg: str):
        await _update_status_step(status_step, status_history, msg)

    try:
        await status_step.__aenter__()
        await _update_status_step(status_step, status_history, "Sending request to agent...")

        response = await client.send(
            query=message.content,
            conversation_id=conversation_id,
            artifacts=artifacts_catalog,
            on_status=_on_status,
        )

        await status_step.__aexit__(None, None, None)
        await _handle_response(client, response, message.content, conversation_id)

    except Exception as e:
        await status_step.__aexit__(None, None, None)
        await cl.Message(content=f"Error communicating with agent: {e}").send()


_MAX_NEEDS_INFO_DEPTH = 5


async def _handle_response(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
    _depth: int = 0,
):
    if response.status == "needs_info":
        await _handle_needs_info(client, response, original_query, conversation_id, _depth=_depth)
    elif response.status == "plan_ready":
        await _handle_plan_ready(client, response, original_query, conversation_id)
    elif response.status in ("completed", "answer", "recommendation", "success"):
        await _handle_final_response(response)
    elif response.status == "executing":
        await cl.Message(content=response.message or "Agent is executing the plan…").send()
    elif response.status == "error":
        await cl.Message(
            content=f"**Error:** {response.message or 'An error occurred during processing.'}"
        ).send()
    else:
        text = response.message or response.response_text or str(response)
        await cl.Message(content=text).send()


def _coerce_final_text(response: ConversationResponse, artifact_count: int) -> str:
    """Collapse machine-oriented JSON payloads into compact user-facing text."""
    candidate = response.report or response.response_text or response.message or ""
    if isinstance(candidate, dict):
        payload = candidate
    elif isinstance(candidate, list):
        payload = None
    else:
        text = str(candidate or "").strip()
        if not text:
            payload = None
        else:
            try:
                parsed = json.loads(text)
            except Exception:
                return text
            payload = parsed if isinstance(parsed, dict) else None

    if not isinstance(payload, dict):
        return ""

    for key in ("message", "report", "response_text", "summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    agent = str(payload.get("agent") or "").strip()
    final_step = str(payload.get("final_step") or payload.get("status") or "").strip()
    if artifact_count:
        if agent and final_step:
            return f"{agent} {final_step.replace('_', ' ')}. {artifact_count} artifact(s) ready."
        if agent:
            return f"{agent} completed. {artifact_count} artifact(s) ready."
        return f"{artifact_count} artifact(s) ready."

    if agent and final_step:
        return f"{agent} {final_step.replace('_', ' ')}."
    if final_step:
        return final_step.replace("_", " ").strip().capitalize() + "."
    return ""


async def _handle_needs_info(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
    *,
    _depth: int = 0,
):
    if _depth >= _MAX_NEEDS_INFO_DEPTH:
        await cl.Message(content="Too many consecutive follow-up requests. Please start a new query.").send()
        return

    questions = response.followup_questions or []
    if not questions:
        if response.message:
            await cl.Message(content=response.message).send()
        return

    form_fields = []
    for q in questions:
        field = {
            "id": q.get("field", q.get("id", q.get("question", ""))),
            "label": q.get("question", q.get("label", "")),
            "input_type": q.get("type", q.get("input_type", "text")),
            "required": bool(q.get("required", True)),
        }
        if isinstance(q.get("options"), list):
            field["options"] = [
                opt if isinstance(opt, dict) else {"label": str(opt), "value": str(opt)}
                for opt in q["options"]
            ]
        if "default" in q:
            field["default"] = q["default"]
        if q.get("description"):
            field["help"] = q["description"]
        form_fields.append(field)

    element = cl.CustomElement(
        name="DynamicForm",
        display="inline",
        props={
            "title": response.message or "Additional information needed",
            "fields": form_fields,
            "submitLabel": "Submit",
            "formId": f"followup_{conversation_id}",
        },
    )
    ask = cl.AskElementMessage(
        content=response.message or "Please provide the following information:",
        element=element,
        timeout=600,
        raise_on_timeout=False,
    )
    submission = await ask.send()
    if not submission:
        await cl.Message(content="Follow-up form timed out.").send()
        return
    if not submission.get("submitted"):
        await cl.Message(content="Follow-up form cancelled.").send()
        return

    followup_answers = {
        key: value
        for key, value in submission.items()
        if key != "submitted"
    }
    followup_history: List[str] = []
    followup_step = cl.Step(name="Submitting follow-up answers...", type="tool")

    async def _on_followup_status(msg: str):
        await _update_status_step(followup_step, followup_history, msg)

    try:
        await followup_step.__aenter__()
        await _update_status_step(followup_step, followup_history, "Submitting follow-up answers...")
        next_response = await client.send(
            query=original_query,
            conversation_id=conversation_id,
            followup_answers=followup_answers,
            artifacts=cl.user_session.get("artifacts", []),
            on_status=_on_followup_status,
        )
        await followup_step.__aexit__(None, None, None)
    except Exception as exc:
        await followup_step.__aexit__(type(exc), exc, exc.__traceback__)
        await cl.Message(content=f"Error submitting follow-up answers: {exc}").send()
        return

    await _handle_response(client, next_response, original_query, conversation_id, _depth=_depth + 1)


async def _handle_plan_ready(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
):
    plan = response.plan or {}

    plan_viewer = cl.CustomElement(
        name="PlanViewer",
        display="inline",
        props={"plan": plan, "stepStatuses": {}},
    )
    await cl.Message(
        content=response.message or "Here's the proposed execution plan:",
        elements=[plan_viewer],
    ).send()

    if not settings.auto_approve_steps:
        res = await cl.AskActionMessage(
            content="Do you want to proceed with this plan?",
            actions=[
                cl.Action(name="approve", payload={"value": "approve"}, label="Approve & Execute"),
                cl.Action(name="reject", payload={"value": "reject"}, label="Reject"),
            ],
        ).send()
        approved = res and res.get("name") == "approve"
    else:
        approved = True

    if not approved:
        await cl.Message(content="Plan rejected.").send()
        return

    artifacts_catalog = cl.user_session.get("artifacts", [])
    exec_history: List[str] = []
    exec_step = cl.Step(name="Executing plan...", type="tool")
    step_statuses: dict = {}
    steps = plan.get("steps", []) if isinstance(plan, dict) else []

    async def _on_exec_status(msg: str):
        await _update_status_step(exec_step, exec_history, msg)
        _update_step_statuses(step_statuses, steps, msg)

    try:
        await exec_step.__aenter__()
        await _update_status_step(exec_step, exec_history, "Executing plan...")

        exec_response = await client.send(
            query=original_query,
            conversation_id=conversation_id,
            plan_approved=True,
            artifacts=artifacts_catalog,
            on_status=_on_exec_status,
        )

        await exec_step.__aexit__(None, None, None)
        await _handle_response(client, exec_response, original_query, conversation_id)
    except Exception as e:
        await exec_step.__aexit__(None, None, None)
        await cl.Message(content=f"Error during plan execution: {e}").send()


def _update_step_statuses(statuses: dict, steps: list, status_msg: str):
    msg_lower = status_msg.lower()
    for i, step in enumerate(steps):
        name = step if isinstance(step, str) else (step.get("name", "") or step.get("agent", ""))
        if not name:
            continue
        if name.lower() in msg_lower:
            if "complet" in msg_lower or "finish" in msg_lower or "done" in msg_lower:
                statuses[i] = "completed"
            elif "fail" in msg_lower or "error" in msg_lower:
                statuses[i] = "failed"
            else:
                statuses[i] = "running"
                for j in range(i):
                    if statuses.get(j) != "failed":
                        statuses[j] = "completed"


async def _handle_final_response(response: ConversationResponse):
    artifacts_to_render = response.new_artifacts or response.artifacts or []
    text = _coerce_final_text(response, len(artifacts_to_render))
    elements = []

    if response.artifacts:
        cl.user_session.set("artifacts", response.artifacts)
    if artifacts_to_render:
        artifact_elements, artifact_text = await render_artifacts(artifacts_to_render)
        elements.extend(artifact_elements)
        if artifact_text:
            text = f"{text}\n\n---\n{artifact_text}".strip() if text else artifact_text

    if response.recommended_materials:
        materials = "\n".join(f"- {m}" for m in response.recommended_materials)
        text += f"\n\n**Recommended Materials:**\n{materials}"

    metadata = response.message_metadata or {}
    suggestions = metadata.get("follow_up_suggestions", [])
    if suggestions:
        elements.append(
            cl.CustomElement(
                name="FollowUpSuggestions",
                props={"suggestions": suggestions, "title": "What would you like to do next?"},
            )
        )

    if text or elements:
        await cl.Message(content=text, elements=elements).send()


async def render_artifacts(
    artifacts: List[Dict[str, Any]],
) -> tuple[list, str]:
    """Render artifact references into Chainlit elements and inline text.

    Routes each artifact through the visualization plugin system first.
    Falls back to text rendering for data, reports, references, PDFs, and
    generic downloadable files.
    """
    elements: list = []
    text_parts: list[str] = []

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        metadata = artifact.get("metadata") or {}
        if metadata.get("kind") == "conversation_message":
            continue
        if artifact.get("name") == "conversation_message":
            continue

        uri = artifact.get("uri", "")
        name = artifact.get("name", "Artifact")
        mime_type = (artifact.get("mime_type") or "").lower()
        json_type = artifact.get("json_type") or (artifact.get("metadata") or {}).get("json_type")
        description = artifact.get("description", "")

        # Try visualization plugin system first
        element = await _plugins.render_artifact(artifact)
        if element is not None:
            elements.append(element)
            continue

        # Fallback: text-based rendering for non-visual artifact types
        artifact_type = _classify_artifact(mime_type)

        if artifact_type == "pdf":
            el = await _render_pdf_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}** (PDF): `{uri}`")

        elif artifact_type == "data":
            data_content = artifact.get("json_body")
            if data_content:
                formatted = json.dumps(data_content, indent=2, default=str)
                heading = f"**{name}:**"
                if json_type:
                    heading += f" `{json_type}`"
                text_parts.append(f"{heading}\n```json\n{formatted}\n```")
            else:
                text_parts.append(f"- **{name}**: {description or uri}")

        elif artifact_type == "report":
            report_text = description
            if report_text:
                text_parts.append(f"### {name}\n{report_text}")
            else:
                text_parts.append(f"- **{name}**: {description or uri}")

        elif artifact_type == "file":
            el = _render_file_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}**: `{uri}`")

        elif artifact_type == "reference":
            text_parts.append(_render_reference_artifact(name, uri, description, metadata))

        else:
            # No plugin and no known text type — tell the user and offer a download
            label = json_type or mime_type or "unknown"
            line = f"📎 **{name}** — no viewer available for `{label}`"
            if description:
                line += f"\n  > {description}"
            el = _render_file_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                line += f"\n  `{uri}`" if uri else ""
            text_parts.append(line)

    return elements, "\n".join(text_parts)


def _classify_artifact(mime_type: str) -> str:
    """Classify artifact for MIME-driven fallback rendering."""
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type in ("application/json", "text/csv"):
        return "data"
    if mime_type in ("text/markdown", "text/plain"):
        return "report"
    if mime_type in (
        "application/octet-stream",
        "application/zip",
        "application/gzip",
        "text/csv",
    ):
        return "file"

    return "unknown"


async def _render_pdf_artifact(uri: str, name: str) -> Optional[Any]:
    try:
        if uri.startswith("file://"):
            path = Path(uri[7:])
        elif uri.startswith("/"):
            path = Path(uri)
        else:
            path = None

        if path and path.exists():
            return cl.Pdf(name=name, display="inline", path=str(path))

        if uri.startswith("http"):
            async with httpx.AsyncClient(timeout=60) as http:
                resp = await http.get(uri)
                resp.raise_for_status()
            tmp = Path(tempfile.mkdtemp()) / (name or "document.pdf")
            tmp.write_bytes(resp.content)
            return cl.Pdf(name=name, display="inline", path=str(tmp))
    except Exception:
        pass
    return None


def _render_file_artifact(uri: str, name: str) -> Optional[Any]:
    if uri.startswith("file://"):
        path = Path(uri[7:])
    elif uri.startswith("/"):
        path = Path(uri)
    else:
        return None
    if path.exists():
        return cl.File(name=name, path=str(path), display="inline")
    return None


def _render_reference_artifact(name: str, uri: str, description: str, metadata: dict) -> str:
    source = metadata.get("source", "")
    section = metadata.get("section", "")
    page = metadata.get("page", "")

    parts = [f"**[{name}]**"]
    if description:
        parts.append(f" {description}")
    citation_parts = []
    if source:
        citation_parts.append(source)
    if section:
        citation_parts.append(f"Section: {section}")
    if page:
        citation_parts.append(f"p. {page}")
    if uri:
        citation_parts.append(f"[link]({uri})" if uri.startswith("http") else f"`{uri}`")
    if citation_parts:
        parts.append(f" — *{', '.join(citation_parts)}*")

    return "".join(parts)
