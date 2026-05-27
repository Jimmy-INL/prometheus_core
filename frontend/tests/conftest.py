"""Shared fixtures for frontend tests."""

import pytest
from pathlib import Path
import sys
import types


def _install_chainlit_stub() -> None:
    chainlit = types.ModuleType("chainlit")
    chainlit.__path__ = []
    chainlit.Action = object
    chainlit.AskActionMessage = object
    chainlit.AskElementMessage = object
    chainlit.ChatSettings = object
    chainlit.CustomElement = object
    chainlit.File = object
    chainlit.Message = object
    chainlit.Pdf = object
    chainlit.Step = object
    chainlit.user_session = types.SimpleNamespace(
        get=lambda *args, **kwargs: None,
        set=lambda *args, **kwargs: None,
    )

    input_widget = types.ModuleType("chainlit.input_widget")
    input_widget.Select = object
    input_widget.Switch = object
    input_widget.Tab = object

    chainlit.input_widget = input_widget
    sys.modules["chainlit"] = chainlit
    sys.modules["chainlit.input_widget"] = input_widget


try:
    import chainlit  # noqa: F401
except ModuleNotFoundError:
    _install_chainlit_stub()


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a small temp file for hash/cache tests."""
    f = tmp_path / "sample.txt"
    f.write_text("hello world")
    return f


@pytest.fixture
def sample_config_yaml(tmp_path: Path) -> Path:
    """Write a minimal config.yml for settings tests."""
    config = tmp_path / "config.yml"
    config.write_text(
        "chat-intro: Welcome\nchat-suggestion-title: Try these\nworkflow-suggestions:\n  - Run MOOSE\n  - Run Alchemy\n"
    )
    return config
