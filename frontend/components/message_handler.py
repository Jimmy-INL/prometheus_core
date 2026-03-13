import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chainlit as cl
import httpx

from components.exodus_integration import process_exodus_upload
from components.ifc_integration import process_ifc_upload, format_file_size

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
    # --- File upload handling (unchanged) ---
    if message.elements:
        for element in message.elements:
            if element.name and element.name.lower().endswith((".exo", ".e")):
                try:
                    await cl.Message(content=f"Processing Exodus file: **{element.name}**...").send()
                    dataset = await process_exodus_upload(Path(element.path))
                    viewer = dataset.to_chainlit_element()

                    meta = dataset.metadata
                    info_lines = [
                        f"**Exodus File Loaded: {element.name}**",
                        f"- Timesteps: {meta.get('num_timesteps', 0)}",
                        f"- Nodes: {meta.get('num_nodes', 0):,}",
                        f"- Elements: {meta.get('num_elements', 0):,}",
                    ]
                    nodal_vars = meta.get("nodal_variables", [])
                    elem_vars = meta.get("element_variables", [])
                    if nodal_vars:
                        info_lines.append(
                            f"- Nodal variables: {', '.join(nodal_vars[:5])}{'...' if len(nodal_vars) > 5 else ''}"
                        )
                    if elem_vars:
                        info_lines.append(
                            f"- Element variables: {', '.join(elem_vars[:5])}{'...' if len(elem_vars) > 5 else ''}"
                        )
                    await cl.Message(content="\n".join(info_lines), elements=[viewer]).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to process Exodus file: {e}").send()

                if not message.content.strip():
                    return

            elif element.name and element.name.lower().endswith(".pdf"):
                try:
                    pdf_element = cl.Pdf(name=element.name, display="inline", path=element.path)
                    await cl.Message(content=f"**PDF Loaded: {element.name}**", elements=[pdf_element]).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to display PDF: {e}").send()

                if not message.content.strip():
                    return

            elif element.name and element.name.lower().endswith(".ifc"):
                try:
                    await cl.Message(content=f"Processing IFC file: **{element.name}**...").send()
                    dataset = await process_ifc_upload(Path(element.path))
                    viewer = dataset.to_chainlit_element()
                    info_lines = [
                        f"**IFC File Loaded: {element.name}**",
                        f"- File size: {format_file_size(dataset.file_size)}",
                    ]
                    await cl.Message(content="\n".join(info_lines), elements=[viewer]).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to process IFC file: {e}").send()

                if not message.content.strip():
                    return

    # --- Text query → A2A client-agent ---
    conversation_id = cl.user_session.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        cl.user_session.set("conversation_id", conversation_id)

    artifacts_catalog = cl.user_session.get("artifacts", [])
    client = _get_a2a_client()

    # Status step for showing progress updates during long-running calls
    status_step = cl.Step(name="Processing", type="tool")

    async def _on_status(msg: str):
        status_step.output = msg
        await status_step.update()

    try:
        await status_step.__aenter__()
        status_step.output = "Sending request to agent..."
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
    """Handle a ConversationResponse based on its status."""

    if response.status == "needs_info":
        await _handle_needs_info(client, response, original_query, conversation_id)

    elif response.status == "plan_ready":
        await _handle_plan_ready(client, response, original_query, conversation_id)

    elif response.status in ("completed", "answer", "recommendation"):
        await _handle_final_response(response)

    elif response.status == "executing":
        msg = response.message or "Agent is executing the plan..."
        await cl.Message(content=msg).send()

    elif response.status == "error":
        error_msg = response.message or "An error occurred during processing."
        await cl.Message(content=f"**Error:** {error_msg}").send()

    else:
        text = response.message or response.response_text or str(response)
        await cl.Message(content=text).send()


async def _handle_needs_info(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
):
    """Handle follow-up questions from the agent."""
    questions = response.followup_questions or []

    if not questions:
        # No structured questions, just show the message
        if response.message:
            await cl.Message(content=response.message).send()
        return

    # Show follow-up questions using DynamicForm for rich input
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

    form_props = {
        "title": response.message or "Additional information needed",
        "fields": form_fields,
        "submitLabel": "Submit",
        "formId": f"followup_{conversation_id}",
    }

    element = cl.CustomElement(name="DynamicForm", display="inline", props=form_props)
    await cl.Message(content=response.message or "Please provide the following information:", elements=[element]).send()

    # Wait for form submission via on_message (user will type or submit form)
    # The form data comes back as the next user message, handled by the main loop


async def _handle_plan_ready(
    client: A2AClient,
    response: ConversationResponse,
    original_query: str,
    conversation_id: str,
):
    """Show plan and ask for user approval using PlanViewer."""
    plan = response.plan or {}

    # Show plan using the rich PlanViewer component
    plan_viewer = cl.CustomElement(
        name="PlanViewer",
        display="inline",
        props={"plan": plan, "stepStatuses": {}},
    )

    await cl.Message(
        content=response.message or "Here's the proposed execution plan:",
        elements=[plan_viewer],
    ).send()

    # Ask for approval
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

    # Send approval back to agent with status polling
    artifacts_catalog = cl.user_session.get("artifacts", [])
    exec_step = cl.Step(name="Executing Plan", type="tool")

    # Track step statuses for real-time updates
    step_statuses = {}
    steps = plan.get("steps", []) if isinstance(plan, dict) else []

    async def _on_exec_status(msg: str):
        exec_step.output = msg
        await exec_step.update()
        # Try to infer step progress from status messages
        _update_step_statuses(step_statuses, steps, msg)

    try:
        await exec_step.__aenter__()
        exec_step.output = "Executing plan..."
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
    """Infer step execution progress from status update messages."""
    msg_lower = status_msg.lower()
    for i, step in enumerate(steps):
        step_name = step if isinstance(step, str) else (step.get("name", "") or step.get("agent", ""))
        if not step_name:
            continue
        if step_name.lower() in msg_lower:
            if "complet" in msg_lower or "finish" in msg_lower or "done" in msg_lower:
                statuses[i] = "completed"
            elif "fail" in msg_lower or "error" in msg_lower:
                statuses[i] = "failed"
            else:
                statuses[i] = "running"
                # Mark previous steps as completed
                for j in range(i):
                    if statuses.get(j) != "failed":
                        statuses[j] = "completed"


async def _handle_final_response(response: ConversationResponse):
    """Handle completed/answer/recommendation responses."""
    # Primary text content
    text = response.report or response.response_text or response.message or ""

    elements = []

    # Show memory context if available
    memory_element = _build_memory_element(response)
    if memory_element:
        elements.append(memory_element)

    # Render artifacts
    if response.artifacts:
        cl.user_session.set("artifacts", response.artifacts)
        artifact_elements, artifact_text = await render_artifacts(response.artifacts)
        elements.extend(artifact_elements)
        if artifact_text:
            text += "\n\n---\n" + artifact_text

    # Show recommended materials if present
    if response.recommended_materials:
        materials = "\n".join(f"- {m}" for m in response.recommended_materials)
        text += f"\n\n**Recommended Materials:**\n{materials}"

    # Show follow-up suggestions if metadata provides them
    metadata = response.message_metadata or {}
    suggestions = metadata.get("follow_up_suggestions", [])
    if suggestions:
        suggestion_element = cl.CustomElement(
            name="FollowUpSuggestions",
            props={"suggestions": suggestions, "title": "What would you like to do next?"},
        )
        elements.append(suggestion_element)

    if text or elements:
        await cl.Message(content=text, elements=elements).send()


def _build_memory_element(response: ConversationResponse):
    """Build a MemoryCards element showing memory context for the response.

    Memory counts come from two places in the client-agent response:
    - num_memories_stored → tool_results (added after execution)
    - num_memories_retrieved → plan dict (set during planning)
    """
    tool_results = response.tool_results or {}
    plan = response.plan or {}
    num_stored = tool_results.get("num_memories_stored", 0)
    # num_memories_retrieved is in the plan, not tool_results
    num_retrieved = plan.get("num_memories_retrieved", 0)

    if not num_retrieved and not num_stored:
        return None

    # Try to fetch recently stored factoids from Redis for display
    factoids = []
    if num_stored > 0 and _memory_client.available:
        recent = _memory_client.get_all_factoids(limit=num_stored)
        for mem in recent[:num_stored]:
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
    """Render artifact references into Chainlit elements and text.

    Routes each artifact to the appropriate viewer based on type/mime/tags:
    - ifc → IFCViewer.jsx (via process_ifc_upload)
    - exodus → ExodusViewer.jsx (via process_exodus_upload)
    - pdf/document → cl.Pdf element or download link
    - data → formatted JSON code block
    - report → inline markdown
    - mermaid → MermaidViewer.jsx
    """
    elements: list = []
    text_parts: list[str] = []

    for artifact in artifacts:
        uri = artifact.get("uri", "")
        name = artifact.get("name", "Artifact")
        mime_type = (artifact.get("mime_type") or "").lower()
        tags = [t.lower() for t in (artifact.get("tags") or [])]
        description = artifact.get("description", "")
        metadata = artifact.get("metadata") or {}
        artifact_type = _classify_artifact(uri, mime_type, tags, metadata)

        if artifact_type == "ifc":
            el = await _render_ifc_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}** (IFC model): `{uri}`")

        elif artifact_type == "exodus":
            el = await _render_exodus_artifact(uri, name)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}** (Exodus mesh): `{uri}`")

        elif artifact_type == "pdf":
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

        elif artifact_type == "mermaid":
            chart = metadata.get("content", metadata.get("chart", ""))
            if chart:
                elements.append(
                    cl.CustomElement(
                        name="MermaidViewer",
                        display="inline",
                        props={"chart": chart},
                    )
                )
            else:
                text_parts.append(f"- **{name}** (diagram): {description}")

        elif artifact_type == "file":
            el = _render_file_artifact(uri, name, mime_type, artifact.get("size_bytes"))
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}**: `{uri}`")

        elif artifact_type == "reference":
            ref_text = _render_reference_artifact(name, uri, description, metadata)
            text_parts.append(ref_text)

        elif artifact_type == "visualization":
            el = await _render_visualization_artifact(uri, name, tags, metadata)
            if el:
                elements.append(el)
            else:
                text_parts.append(f"- **{name}** (visualization): {description or uri}")

        else:
            if description:
                text_parts.append(f"- **{name}**: {description}")
            elif uri:
                text_parts.append(f"- **{name}**: `{uri}`")

    return elements, "\n".join(text_parts)


def _classify_artifact(uri: str, mime_type: str, tags: list, metadata: dict) -> str:
    """Determine artifact type for routing to the correct renderer."""
    # Check explicit type in metadata first
    explicit_type = (metadata.get("type") or "").lower()
    if explicit_type:
        return explicit_type

    uri_lower = uri.lower()

    if uri_lower.endswith(".ifc") or "ifc" in tags or "model/ifc" in mime_type:
        return "ifc"
    if uri_lower.endswith((".exo", ".e")) or "exodus" in tags:
        return "exodus"
    if uri_lower.endswith(".pdf") or "application/pdf" in mime_type or "pdf" in tags or "document" in tags:
        return "pdf"
    if mime_type in ("application/json", "text/csv") or "data" in tags:
        return "data"
    if "report" in tags or mime_type in ("text/markdown", "text/plain"):
        return "report"
    if "mermaid" in tags or "mermaid" in mime_type:
        return "mermaid"
    if "reference" in tags or "citation" in tags:
        return "reference"
    if "visualization" in tags or "vtk" in tags:
        return "visualization"
    # Generic downloadable files
    if uri_lower and any(uri_lower.endswith(ext) for ext in (
        ".csv", ".xlsx", ".zip", ".tar", ".gz", ".txt", ".log", ".inp", ".i",
    )):
        return "file"

    return "unknown"


def _resolve_uri_to_path(uri: str) -> Optional[Path]:
    """Resolve a file:// URI or absolute path to a Path object."""
    if uri.startswith("file://"):
        return Path(uri[7:])
    if uri.startswith("/"):
        return Path(uri)
    return None


async def _render_ifc_artifact(uri: str, name: str):
    """Render an IFC artifact using IFCViewer."""
    try:
        file_path = _resolve_uri_to_path(uri)
        if file_path and file_path.exists():
            dataset = await process_ifc_upload(file_path)
            return dataset.to_chainlit_element()
    except Exception:
        pass
    return None


async def _render_exodus_artifact(uri: str, name: str):
    """Render an Exodus artifact using ExodusViewer."""
    try:
        file_path = _resolve_uri_to_path(uri)
        if file_path and file_path.exists():
            dataset = await process_exodus_upload(file_path)
            return dataset.to_chainlit_element()
    except Exception:
        pass
    return None


async def _render_pdf_artifact(uri: str, name: str):
    """Render a PDF artifact inline."""
    try:
        file_path = _resolve_uri_to_path(uri)
        if file_path and file_path.exists():
            return cl.Pdf(name=name, display="inline", path=str(file_path))
        if uri.startswith("http"):
            async with httpx.AsyncClient(timeout=60) as http_client:
                resp = await http_client.get(uri)
                resp.raise_for_status()
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / (name or "document.pdf")
            tmp_path.write_bytes(resp.content)
            return cl.Pdf(name=name, display="inline", path=str(tmp_path))
    except Exception:
        pass
    return None


def _render_file_artifact(uri: str, name: str, mime_type: str, size_bytes: Optional[int]):
    """Render a downloadable file artifact."""
    file_path = _resolve_uri_to_path(uri)
    if file_path and file_path.exists():
        return cl.File(name=name, path=str(file_path), display="inline")
    return None


def _render_reference_artifact(name: str, uri: str, description: str, metadata: dict) -> str:
    """Render a reference/citation artifact as formatted markdown text."""
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


async def _render_visualization_artifact(uri: str, name: str, tags: list, metadata: dict):
    """Render a visualization artifact by routing to the correct viewer."""
    # Route to specific viewer based on tags/metadata
    if "exodus" in tags or "vtk" in tags:
        return await _render_exodus_artifact(uri, name)
    if "ifc" in tags:
        return await _render_ifc_artifact(uri, name)
    if "mermaid" in tags:
        chart = metadata.get("content", metadata.get("chart", ""))
        if chart:
            return cl.CustomElement(
                name="MermaidViewer",
                display="inline",
                props={"chart": chart},
            )
    # Default: try ExodusViewer for generic vis files
    return await _render_exodus_artifact(uri, name)
