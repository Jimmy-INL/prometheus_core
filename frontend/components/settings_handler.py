from pathlib import Path

import chainlit as cl

from chainlit.input_widget import Switch, Tab, Select
from components.ifc_integration import process_ifc_upload, format_file_size
from components.exodus_integration import process_exodus_upload

from utils.settings import settings as app_settings


async def configure_settings():
    tabs = [
        Tab(
            id="ui_config",
            label="Config",
            inputs=[
                Select(
                    id="model",
                    label="Model",
                    values=[
                        "None",
                        "gpt-oss-120B (AmSC)",
                        "gpt-oss-120B (INL)",
                        "GPT-5.3 Chat (OpenAI)",
                        "Claude Opus 4.6 (Anthropic)"
                    ],
                    initial_index=0,
                ),
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
                        values=["None"],
                        initial_index=0,
                    )
                ],
            )
        )
    await cl.ChatSettings(tabs).send()


async def settings_debug_options(ui_settings):
    debug_feature = ui_settings.get("debug_feature")

    if debug_feature and debug_feature != "None":
        pass
