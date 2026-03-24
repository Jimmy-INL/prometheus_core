from pathlib import Path

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
                    id="approval_type",
                    label="Approval Type",
                    values=[
                        "None",
                        "Workflow Level",
                        "Agent Level"
                    ],
                    initial_index=0,
                ),
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
                        values=["None", "Exodus File", "IFC File"],
                        initial_index=0,
                    )
                ],
            )
        )
    await cl.ChatSettings(tabs).send()


async def settings_debug_options(ui_settings):
    debug_feature = ui_settings.get("debug_feature")

    if debug_feature and debug_feature != "None":
        match debug_feature:
            case "Exodus File":
                await cl.Message(content="Upload an Exodus file to test the viewer.").send()
            case "IFC File":
                await cl.Message(content="Upload an IFC file to test the viewer.").send()
            case _:
                pass
