import json
import tempfile
from pathlib import Path

import chainlit as cl
import httpx
import requests

from components.exodus_integration import process_exodus_upload
from components.ifc_integration import process_ifc_upload, format_file_size

from utils.settings import settings


async def message_handler(message: cl.Message):
    if message.elements:
        for element in message.elements:
            # Check for Exodus file uploads
            if element.name and element.name.lower().endswith((".exo", ".e")):
                # Process the Exodus file upload
                try:
                    await cl.Message(content=f"Processing Exodus file: **{element.name}**...").send()

                    dataset = await process_exodus_upload(Path(element.path))
                    viewer = dataset.to_chainlit_element()

                    # Build info message
                    meta = dataset.metadata
                    num_timesteps = meta.get("num_timesteps", 0)
                    num_nodes = meta.get("num_nodes", 0)
                    num_elements = meta.get("num_elements", 0)
                    nodal_vars = meta.get("nodal_variables", [])
                    elem_vars = meta.get("element_variables", [])

                    info_lines = [
                        f"**Exodus File Loaded: {element.name}**",
                        f"- Timesteps: {num_timesteps}",
                        f"- Nodes: {num_nodes:,}",
                        f"- Elements: {num_elements:,}",
                    ]
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

                # Don't continue with orchestration for pure file uploads
                if not message.content.strip():
                    return

            # Check for PDF file uploads
            elif element.name and element.name.lower().endswith(".pdf"):
                try:
                    pdf_element = cl.Pdf(
                        name=element.name,
                        display="inline",
                        path=element.path,
                    )
                    await cl.Message(
                        content=f"**PDF Loaded: {element.name}**",
                        elements=[pdf_element],
                    ).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to display PDF: {e}").send()

                if not message.content.strip():
                    return

            # Check for IFC file uploads
            elif element.name and element.name.lower().endswith(".ifc"):
                # Process the IFC file upload
                try:
                    await cl.Message(content=f"Processing IFC file: **{element.name}**...").send()

                    dataset = await process_ifc_upload(Path(element.path))
                    viewer = dataset.to_chainlit_element()

                    # Build info message
                    info_lines = [
                        f"**IFC File Loaded: {element.name}**",
                        f"- File size: {format_file_size(dataset.file_size)}",
                    ]

                    await cl.Message(content="\n".join(info_lines), elements=[viewer]).send()

                except Exception as e:
                    await cl.Message(content=f"Failed to process IFC file: {e}").send()

                # Don't continue with orchestration for pure file uploads
                if not message.content.strip():
                    return
    else:
        payload = {"message": message.content, "user_id": "user_123", "context": {}, "files": []}

        try:
            response = requests.post(f"{settings.platform_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.ConnectionError:
            await cl.Message(content="Unable to connect to the backend. Please ensure the backend server is running.").send()
            return
        except requests.exceptions.JSONDecodeError:
            await cl.Message(content=f"Backend returned an invalid response (HTTP {response.status_code}). Check backend logs for details.").send()
            return
        except requests.exceptions.HTTPError:
            await cl.Message(content=f"Backend error (HTTP {response.status_code}). Check backend logs for details.").send()
            return

        if data.get("type") == "workflow":
            await _run_demo_workflow(message.content, data.get("session_id"))
        elif data.get("type") == "fmea_workflow":
            await _run_demo_workflow(message.content, data.get("session_id"), workflow_path="/api/demo/workflow/fmea")
        else:
            await cl.Message(
                content=f"{data['response']}",
            ).send()


async def _stream_workflow_events(client, plan_msg, pending_artifacts, workflow_path="/api/demo/workflow/run", **request_json):
    """Stream a single workflow run request and render events.

    Returns (plan_msg, workflow_id, session_id) so callers can chain
    follow-up requests with the same identifiers.
    """
    current_step = None
    workflow_id = None
    session_id = None

    async with client.stream(
        "POST",
        f"{settings.platform_url}{workflow_path}",
        json=request_json,
    ) as stream:
        workflow_id = stream.headers.get("x-workflow-id", "")
        session_id = stream.headers.get("x-session-id", "")

        async for line in stream.aiter_lines():
            if not line.strip():
                continue

            event = json.loads(line)
            event_type = event.get("event_type")

            if event_type == "workflow_start":
                if plan_msg is None:
                    total = event.get("total_steps", 0)
                    plan_msg = cl.Message(
                        content=f"Creating workflow plan...",
                    )
                    await plan_msg.send()
            elif event_type == "step_start":
                agent = event.get("agent", "Agent")
                prompt = event.get("prompt", "")
                idx = event.get("step_index", 0)
                total = event.get("total_steps", 0)

                current_step = cl.Step(
                    #name=f"Step {idx + 1}/{total}: {agent}",
                    name=f"{agent}",
                    type="tool",
                    parent_id=plan_msg.id,
                    show_input=True,
                )
                current_step.input = prompt
                await current_step.send()

            elif event_type == "step_complete":
                resp_text = event.get("response", "")
                artifact_url = event.get("artifact_url")

                if current_step:
                    current_step.output = resp_text
                    await current_step.update()
                    current_step = None

                if artifact_url:
                    pending_artifacts.append(artifact_url)

            elif event_type == "workflow_complete":
                await cl.Message(
                    content="Workflow completed successfully!",
                ).send()

    return plan_msg, workflow_id, session_id, current_step


async def _run_demo_workflow(trigger_message: str, session_id: str = "", workflow_path: str = "/api/demo/workflow/run"):
    """Stream the demo workflow from the backend and display each step."""
    await cl.Message(
        content=f"Starting workflow: **{trigger_message}",
    ).send()

    pending_artifacts = []
    plan_msg = None

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Phase 1: run only the planning step
            plan_msg, workflow_id, session_id, current_step = await _stream_workflow_events(
                client, plan_msg, pending_artifacts,
                workflow_path=workflow_path,
                message=trigger_message,
                user_id="user_123",
                session_id=session_id,
                end_step=1,
            )

            # Approval gate after planning step
            if not settings.auto_approve_steps:
                ask_msg = cl.AskActionMessage(
                    content="Planning complete. Proceed with this plan?",
                    actions=[
                        cl.Action(name="approve", payload={"value": "approve"}, label="Continue"),
                        cl.Action(name="reject", payload={"value": "reject"}, label="Stop Workflow"),
                    ],
                )
                res = await ask_msg.send()

                if not res or res.get("name") == "reject":
                    await cl.Message(content="Workflow stopped by user.").send()
                    return

                await ask_msg.remove()

            # Phase 2: run remaining steps
            plan_msg, _, _, current_step = await _stream_workflow_events(
                client, plan_msg, pending_artifacts,
                workflow_path=workflow_path,
                message=trigger_message,
                user_id="user_123",
                session_id=session_id,
                workflow_id=workflow_id,
                start_step=1,
            )

        # Display artifacts at the very end, after all steps
        for artifact_url in pending_artifacts:
            if artifact_url.endswith("/ifc"):
                await _display_ifc_artifact(artifact_url, plan_msg)
            elif artifact_url.endswith("/ecar"):
                await _display_pdf_artifact(artifact_url)

    except Exception as e:
        await cl.Message(content=f"Workflow failed: {e}").send()


async def _display_pdf_artifact(artifact_url: str):
    """Fetch a PDF file from the backend and display it inline."""
    await cl.Message(content="Generating ECAR...").send()

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(f"{settings.platform_url}{artifact_url}")
        resp.raise_for_status()

    filename = "report.pdf"
    cd = resp.headers.get("content-disposition", "")
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip().strip('"')

    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / filename
    tmp_path.write_bytes(resp.content)

    pdf_element = cl.Pdf(name=filename, display="inline", path=str(tmp_path))
    await cl.Message(
        content=f"**Report Generated: {filename}**",
        elements=[pdf_element],
    ).send()


async def _display_ifc_artifact(artifact_url: str, plan_msg: cl.Message | None = None):
    """Fetch an IFC file via DeepLynx and display it with IFCViewer."""
    await cl.Message(content="Rendering 3D model...").send()

    async with httpx.AsyncClient(timeout=120) as client:
        # Trigger upload to DeepLynx
        upload_step = cl.Step(
            name="DeepLynx Upload",
            type="tool",
            parent_id=plan_msg.id if plan_msg else None,
            show_input=True,
        )
        upload_step.input = "Uploading IFC file to DeepLynx"
        await upload_step.send()

        resp = await client.get(f"{settings.platform_url}{artifact_url}")
        resp.raise_for_status()
        upload_result = resp.json()

        upload_step.output = json.dumps(upload_result, indent=2)
        await upload_step.update()

        # Download the file from DeepLynx
        download_step = cl.Step(
            name="DeepLynx Download",
            type="tool",
            parent_id=plan_msg.id if plan_msg else None,
            show_input=True,
        )
        download_step.input = "Downloading IFC file from DeepLynx"
        await download_step.send()

        resp = await client.get(f"{settings.platform_url}/demo/ifc-download")
        resp.raise_for_status()
        download_result = resp.json()

        download_step.output = json.dumps(download_result, indent=2)
        await download_step.update()

    file_path = Path(download_result["file_path"])

    dataset = await process_ifc_upload(file_path)
    viewer = dataset.to_chainlit_element()

    await cl.Message(
        content=f"**3D Model Generated: {file_path.name}**\n- File size: {format_file_size(dataset.file_size)}",
        elements=[viewer],
    ).send()
