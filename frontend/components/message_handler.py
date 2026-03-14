import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chainlit as cl
import httpx

import plugins as _plugins
from utils.a2a_client import A2AClient, ConversationResponse
from utils.memory_client import MemoryClient
from utils.settings import settings

_memory_client = MemoryClient(settings.redis_url)


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

    status_step = cl.Step(name="Processing", type="tool")

    async def _on_status(msg: str):
        status_step.output = msg
        await status_step.update()

    try:
        await status_step.__aenter__()
        status_step.output = "Sending request to agent…"
        await status_step.update()

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


async def _handle_response(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
):
    if response.status == "needs_info":
        await _handle_needs_info(client, response, original_query, conversation_id)
    elif response.status == "plan_ready":
        await _handle_plan_ready(client, response, original_query, conversation_id)
    elif response.status in ("completed", "answer", "recommendation"):
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


async def _handle_needs_info(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
):
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
            "type": q.get("type", "text"),
        }
        if "options" in q:
            field["options"] = q["options"]
        if "default" in q:
            field["default"] = q["default"]
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
    await cl.Message(
        content=response.message or "Please provide the following information:",
        elements=[element],
    ).send()


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
    exec_step = cl.Step(name="Executing Plan", type="tool")
    step_statuses: dict = {}
    steps = plan.get("steps", []) if isinstance(plan, dict) else []

    async def _on_exec_status(msg: str):
        exec_step.output = msg
        await exec_step.update()
        _update_step_statuses(step_statuses, steps, msg)

    try:
        await exec_step.__aenter__()
        exec_step.output = "Executing plan…"
        await exec_step.update()

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
    text = response.report or response.response_text or response.message or ""
    elements = []

    memory_element = _build_memory_element(response)
    if memory_element:
        elements.append(memory_element)

    if response.artifacts:
        cl.user_session.set("artifacts", response.artifacts)
        artifact_elements, artifact_text = await render_artifacts(response.artifacts)
        elements.extend(artifact_elements)
        if artifact_text:
            text += "\n\n---\n" + artifact_text

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


def _build_memory_element(response: ConversationResponse):
    tool_results = response.tool_results or {}
    plan = response.plan or {}
    num_stored = tool_results.get("num_memories_stored", 0)
    num_retrieved = plan.get("num_memories_retrieved", 0)

    if not num_retrieved and not num_stored:
        return None

    factoids = []
    if num_stored > 0 and _memory_client.available:
        for mem in _memory_client.get_all_factoids(limit=num_stored)[:num_stored]:
            factoids.append({
                "content": mem.get("content", ""),
                "material_id": mem.get("material_id"),
                "analysis_type": mem.get("analysis_type"),
                "factoid_type": mem.get("factoid_type"),
                "confidence": mem.get("confidence"),
            })

    return cl.CustomElement(
        name="MemoryCards",
        display="inline",
        props={
            "factoids": factoids,
            "numRetrieved": num_retrieved,
            "numStored": num_stored,
            "title": "Memory Context",
        },
    )


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

        uri = artifact.get("uri", "")
        name = artifact.get("name", "Artifact")
        mime_type = (artifact.get("mime_type") or "").lower()
        tags = [t.lower() for t in (artifact.get("tags") or [])]
        description = artifact.get("description", "")
        metadata = artifact.get("metadata") or {}

        # Try visualization plugin system first
        element = await _plugins.render_artifact(artifact)
        if element is not None:
            elements.append(element)
            continue

        # Fallback: text-based rendering for non-visual artifact types
        artifact_type = _classify_artifact(uri, mime_type, tags, metadata)

        if artifact_type == "pdf":
            el = await _render_pdf_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}** (PDF): `{uri}`")

        elif artifact_type == "data":
            data_content = metadata.get("content", metadata.get("data"))
            if data_content:
                formatted = json.dumps(data_content, indent=2, default=str)
                text_parts.append(f"**{name}:**\n```json\n{formatted}\n```")
            else:
                text_parts.append(f"- **{name}**: {description or uri}")

        elif artifact_type == "report":
            report_text = metadata.get("content", metadata.get("text", description))
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
            label = mime_type or (tags[0] if tags else "unknown")
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


def _classify_artifact(uri: str, mime_type: str, tags: list, metadata: dict) -> str:
    """Classify artifact for text-based fallback rendering."""
    # Only handle types not covered by the plugin system
    explicit_type = (metadata.get("type") or "").lower()
    if explicit_type in ("pdf", "data", "report", "reference", "file"):
        return explicit_type

    uri_lower = uri.lower()

    if uri_lower.endswith(".pdf") or "application/pdf" in mime_type or "pdf" in tags or "document" in tags:
        return "pdf"
    if mime_type in ("application/json", "text/csv") or "data" in tags:
        return "data"
    if "report" in tags or mime_type in ("text/markdown", "text/plain"):
        return "report"
    if "reference" in tags or "citation" in tags:
        return "reference"
    if uri_lower and any(uri_lower.endswith(ext) for ext in (
        ".csv", ".xlsx", ".zip", ".tar", ".gz", ".txt", ".log", ".inp", ".i",
    )):
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
