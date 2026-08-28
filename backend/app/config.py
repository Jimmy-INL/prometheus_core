import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import yaml
from pydantic_settings import BaseSettings

CONFIG_PATH = os.environ.get(
    "PROMETHEUS_CONFIG_PATH",
    str(Path(__file__).parent / "config.yml"),
)
MAX_UPLOAD_BYTES_ENV = "PROMETHEUS_MAX_UPLOAD_BYTES"
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def read_config(config_file_path: str) -> dict[str, Any]:
    try:
        with open(config_file_path, "r") as f:
            data = yaml.safe_load(f) or {}
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {config_file_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML: {e}")


def _positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def get_max_upload_bytes(data: dict[str, Any]) -> int:
    env_value = os.environ.get(MAX_UPLOAD_BYTES_ENV)
    if env_value is not None and env_value.strip():
        return _positive_int(env_value, MAX_UPLOAD_BYTES_ENV)
    return _positive_int(data.get("max-upload-bytes", DEFAULT_MAX_UPLOAD_BYTES), "max-upload-bytes")


def _jwt_secret(data: dict[str, Any]) -> str:
    # Prefer a dedicated secret, then reuse Chainlit's, then the config file value.
    return (
        os.environ.get("BACKEND_JWT_SECRET")
        or os.environ.get("CHAINLIT_AUTH_SECRET")
        or data.get("jwt-secret", "")
    )


def _dev_cors_origins() -> list[str]:
    """Explicit dev CORS origins (AU-9).

    A wildcard ``*`` with credentials is rejected by browsers and is a footgun, so in
    debug we enumerate the local dev origins instead. Override via
    ``BACKEND_DEV_ORIGINS`` (comma-separated); defaults cover the Vite dev server
    on its common ports.
    """
    raw = os.environ.get("BACKEND_DEV_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5150",
        "http://127.0.0.1:5150",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def _redis_url(data: dict[str, Any]) -> str:
    """Resolve the Redis URL, folding in ``REDIS_PASSWORD`` when the URL carries no
    credentials.

    The documented setup embeds the password directly in ``REDIS_URL`` (``.env.example``),
    in which case this is a no-op. It only activates the footgun case (DEP-1): a deploy
    sets ``REDIS_PASSWORD`` but leaves ``REDIS_URL`` at a password-less default, which
    would otherwise hit ``NOAUTH`` on every Redis-backed feature. The password is
    URL-encoded since this code path constructs the userinfo itself.
    """
    url: str = os.environ.get("REDIS_URL", data.get("redis-url", "redis://localhost:6379"))
    password = os.environ.get("REDIS_PASSWORD")
    if password and "@" not in urlsplit(url).netloc:
        parts = urlsplit(url)
        netloc = f":{quote(password, safe='')}@{parts.netloc}"
        url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


class Settings(BaseSettings):
    data: dict[str, Any] = read_config(CONFIG_PATH)

    # Content / suggestions
    local_users: list[dict[str, str]] = data.get("local-users", [])
    workflow_suggestions: list[str] = data.get("workflow-suggestions", [])
    chat_suggestion_title: str = data.get("chat-suggestion-title", "")
    chat_intro: str = data.get("chat-intro", "")

    # Upstream client-agent + Redis (env overrides)
    agent_url: str = os.environ.get("CLIENT_AGENT_URL", data.get("agent-url", "http://localhost:8001"))
    agent_secret: str = os.environ.get("AGENT_SECRET", data.get("agent-secret", ""))
    redis_url: str = _redis_url(data)

    # Uploads
    max_upload_bytes: int = get_max_upload_bytes(data)

    # Mesh (Exodus/STL) → VTP conversion cache root (empty = <tempdir>/prometheus-mesh).
    # Overridden by env PROMETHEUS_MESH_CACHE_DIR.
    mesh_cache_dir: str = os.environ.get("PROMETHEUS_MESH_CACHE_DIR", data.get("mesh-cache-dir", ""))

    # Behavior
    debug: bool = data.get("debug", False)
    auto_approve_steps: bool = data.get("auto-approve-steps", False)
    dev_cors_origins: list[str] = _dev_cors_origins()

    # Auth / session
    jwt_secret: str = _jwt_secret(data)
    cookie_name: str = os.environ.get("BACKEND_COOKIE_NAME", data.get("cookie-name", "prometheus_session"))
    token_ttl_seconds: int = _positive_int(
        os.environ.get("BACKEND_TOKEN_TTL_SECONDS", data.get("token-ttl-seconds", 86400)),
        "token-ttl-seconds",
    )


settings = Settings()
