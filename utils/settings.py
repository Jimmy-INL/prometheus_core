import argparse
from typing import Any
from pydantic_settings import BaseSettings
import yaml
from pathlib import Path


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
    data: dict[str, Any] = read_config("/Users/biggbs/projects/c500-prometheus-platform/config.yml")
    local_users: list[dict[str, str]] = [{"username": "admin", "password": "admin", "role": "admin"}]
    workflow_suggestions: list[str] = data["workflow-suggestions"]
    chat_suggestion_title: str = data["chat-suggestion-title"]
    chat_intro: str = data["chat-intro"]
    ifc_data_dir: Path = Path(__file__).parent.parent / "public" / "ifc-data"
    exodus_data_dir: Path = Path(__file__).parent.parent / "public" / "exodus-data"
    platform_url: str = "http://127.0.0.1:8001"
    debug: bool = True
    auto_approve_steps: bool = True
    # auto_approve_steps: bool = False
    agent_names: list[str] = ["MOOSE", "Alchemy", "AutoDONE", "FTL"]


settings = Settings()


def parse_args() -> argparse.Namespace: ...
