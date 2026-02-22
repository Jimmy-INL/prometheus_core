import tempfile
from pathlib import Path

import httpx
import requests
import chainlit as cl

from chainlit.input_widget import Switch, Tab, Select
from components.ifc_integration import process_ifc_upload, format_file_size
from components.exodus_integration import process_exodus_upload

from utils.settings import settings as app_settings


async def configure_settings():
    agent_names = app_settings.agent_names
    agent_switches = [Switch(id=f"use_{name}", label=f"Use {name}", initial=False) for name in agent_names]
    tabs = [
        Tab(
            id="ui_config",
            label="Config",
            inputs=[
                Select(
                    id="Model",
                    label="Model",
                    values=["GPT 5.3", "Claude Opus 4.6"],
                    initial_index=0,
                )
            ],
        ),
        Tab(id="agent_config", label="Enable Agents", inputs=agent_switches),
    ]

    if app_settings.debug:
        tabs.append(
            Tab(
                id="debug",
                label="Debug",
                inputs=[
                    Select(
                        id="debug_feature",
                        label="Test Feature",
                        values=["None", "Form", "Requirements", "Exodus File", "IFC File", "Mermaid Plot", "Graph"],
                        initial_index=0,
                    )
                ],
            )
        )
    await cl.ChatSettings(tabs).send()


async def settings_debug_options(ui_settings):
    debug_feature = ui_settings["debug_feature"]

    if debug_feature and debug_feature != "None":
        match debug_feature:
            case "Form":
                await cl.Message(content="").remove()
                response = requests.get(f"{app_settings.platform_url}/demo/autodone")
                form_props = response.json()
                element = cl.CustomElement(name="DynamicForm", display="inline", props=form_props)

                await cl.Message(content="", elements=[element]).send()
            case "Requirements":
                await cl.Message(content="").remove()
                response = requests.get(f"{app_settings.platform_url}/demo/nuclear-system-design")
                form_props = response.json()
                element = cl.CustomElement(name="DynamicForm", display="inline", props=form_props)

                await cl.Message(content="", elements=[element]).send()
            case "Exodus File":
                await cl.Message(content="Fetching Exodus file from API...").send()
                try:
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.get(f"{app_settings.platform_url}/demo/exodus")
                        resp.raise_for_status()

                    # Extract filename from Content-Disposition or fall back
                    cd = resp.headers.get("content-disposition", "")
                    filename = "sample.e"
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip().strip('"')

                    # Write to temp file and process through existing pipeline
                    tmp_dir = Path(tempfile.mkdtemp())
                    tmp_path = tmp_dir / filename
                    tmp_path.write_bytes(resp.content)

                    dataset = await process_exodus_upload(tmp_path)
                    viewer = dataset.to_chainlit_element()

                    meta = dataset.metadata
                    info_lines = [
                        f"**Exodus File Loaded: {filename}**",
                        f"- Timesteps: {meta.get('num_timesteps', 0)}",
                        f"- Nodes: {meta.get('num_nodes', 0):,}",
                        f"- Elements: {meta.get('num_elements', 0):,}",
                    ]

                    await cl.Message(
                        content="\n".join(info_lines),
                        elements=[viewer],
                    ).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to load Exodus file: {e}").send()
            case "IFC File":
                await cl.Message(content="Fetching IFC file from API...").send()
                try:
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.get(f"{app_settings.platform_url}/demo/ifc")
                        resp.raise_for_status()

                    # Extract filename from Content-Disposition or fall back
                    cd = resp.headers.get("content-disposition", "")
                    filename = "sample.ifc"
                    if "filename=" in cd:
                        filename = cd.split("filename=")[-1].strip().strip('"')

                    # Write to temp file and process through existing pipeline
                    tmp_dir = Path(tempfile.mkdtemp())
                    tmp_path = tmp_dir / filename
                    tmp_path.write_bytes(resp.content)

                    dataset = await process_ifc_upload(tmp_path)
                    viewer = dataset.to_chainlit_element()

                    info_lines = [
                        f"**IFC File Loaded: {filename}**",
                        f"- File size: {format_file_size(dataset.file_size)}",
                    ]

                    await cl.Message(
                        content="\n".join(info_lines),
                        elements=[viewer],
                    ).send()
                except Exception as e:
                    await cl.Message(content=f"Failed to load IFC file: {e}").send()
            case "Mermaid Plot":
                print("mermaid")
            case "Graph":
                print("graph")
            case _:
                print("Unknown status")
