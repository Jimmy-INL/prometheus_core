import argparse
import os
from typing import Any
from pydantic_settings import BaseSettings
import yaml
from pathlib import Path

CONFIG_PATH = os.environ.get(
    "PROMETHEUS_CONFIG_PATH",
    str(Path(__file__).parent.parent / "config.yml"),
)


def read_config(config_file_path: str):
    try:
        with open(config_file_path, "r") as f:
            data = yaml.safe_load(f) or {}
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_file_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML: {e}")


class Settings(BaseSettings):
    data: dict[str, Any] = read_config(CONFIG_PATH)
    local_users: list[dict[str, str]] = data.get("local-users", [])
    workflow_suggestions: list[str] = data["workflow-suggestions"]
    chat_suggestion_title: str = data["chat-suggestion-title"]
    chat_intro: str = data["chat-intro"]
    ifc_data_dir: Path = Path(__file__).parent.parent / "public" / "ifc-data"
    exodus_data_dir: Path = Path(__file__).parent.parent / "public" / "exodus-data"
    platform_url: str = data.get("platform-url", "http://127.0.0.1:8001")
    debug: bool = data.get("debug", True)
    auto_approve_steps: bool = data.get("auto-approve-steps", False)
    agent_names: list[str] = data.get("agent-names", [])


settings = Settings()


def parse_args() -> argparse.Namespace: ...
