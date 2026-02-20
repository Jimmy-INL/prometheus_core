"""Tests for components/settings_handler.py."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from components import settings_handler as handler


@dataclass
class DummySwitch:
    id: str
    label: str
    initial: bool


@dataclass
class DummySelect:
    id: str
    label: str
    values: list[str]
    initial_index: int


@dataclass
class DummyTab:
    id: str
    label: str
    inputs: list


def _install_widgets(monkeypatch):
    monkeypatch.setattr(handler, "Switch", DummySwitch)
    monkeypatch.setattr(handler, "Select", DummySelect)
    monkeypatch.setattr(handler, "Tab", DummyTab)


def _install_message_spy(monkeypatch):
    sent_messages = []

    class DummyMessage:
        def __init__(self, content="", elements=None):
            self.content = content
            self.elements = elements
            sent_messages.append(self)

        async def send(self):
            return self

        async def remove(self):
            return self

    monkeypatch.setattr(handler.cl, "Message", DummyMessage)
    return sent_messages


@pytest.mark.asyncio
async def test_configure_settings_includes_debug_tab(monkeypatch):
    created = []

    class DummyChatSettings:
        def __init__(self, tabs):
            self.tabs = tabs
            self.sent = False
            created.append(self)

        async def send(self):
            self.sent = True
            return self

    _install_widgets(monkeypatch)
    monkeypatch.setattr(handler.cl, "ChatSettings", DummyChatSettings)
    monkeypatch.setattr(handler, "app_settings", SimpleNamespace(agent_names=["MOOSE", "Alchemy"], debug=True))

    await handler.configure_settings()

    assert created and created[0].sent
    tabs = created[0].tabs
    assert [tab.id for tab in tabs] == ["ui_config", "agent_config", "debug"]
    assert [switch.id for switch in tabs[1].inputs] == ["use_MOOSE", "use_Alchemy"]


@pytest.mark.asyncio
async def test_settings_debug_options_form(monkeypatch):
    sent_messages = _install_message_spy(monkeypatch)

    class DummyCustomElement:
        def __init__(self, name, display=None, props=None):
            self.name = name
            self.display = display
            self.props = props

    response = MagicMock()
    response.json.return_value = {"fields": []}
    get = MagicMock(return_value=response)

    monkeypatch.setattr(handler.cl, "CustomElement", DummyCustomElement)
    monkeypatch.setattr(handler.requests, "get", get)
    monkeypatch.setattr(handler, "app_settings", SimpleNamespace(platform_url="http://backend"))

    await handler.settings_debug_options({"debug_feature": "Form"})

    get.assert_called_once_with("http://backend/demo/autodone")
    assert any(msg.elements and msg.elements[0].name == "DynamicForm" for msg in sent_messages)
