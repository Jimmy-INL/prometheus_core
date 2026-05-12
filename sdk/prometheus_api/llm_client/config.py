"""Configuration loading for the provider-agnostic LLM client."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, cast


def _env_flag(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_env_references(value: Any) -> Any:
    """Resolve LiteLLM YAML ``os.environ/NAME`` values when available."""
    if isinstance(value, str) and value.startswith("os.environ/"):
        env_name = value.split("/", 1)[1]
        return os.getenv(env_name, value)
    if isinstance(value, dict):
        return {str(key): _resolve_env_references(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_references(item) for item in value]
    return value


@dataclass(frozen=True)
class FallbackModelConfig:
    """One LiteLLM fallback model entry loaded from ``LLM_CONFIG_FILE``."""

    alias: str
    provider_model: str
    litellm_params: dict[str, Any]


@dataclass
class LLMConfig:
    """Runtime settings for ``LLMClient`` and ``AsyncLLMClient``."""

    proxy_url: str | None = None
    config_file: Path | None = None
    default_model: str = "default"
    debug_log_messages: bool = False
    enable_mlflow_tracing: bool = False
    app_name: str | None = None
    mlflow_trace_tags: dict[str, str] = field(default_factory=dict)
    api_key: str | None = None
    timeout: float = 30.0
    _fallback_models_cache: dict[str, FallbackModelConfig] | None = field(
        default=None, init=False, repr=False
    )

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> "LLMConfig":
        """Build config from supported environment variables."""
        env_file_vars: Mapping[str, str | None] = {}
        if env is None:
            dotenv_path = env_file or Path.cwd() / ".env"
            if dotenv_path.exists():
                dotenv = cast(Any, importlib.import_module("dotenv"))
                env_file_vars = dotenv.dotenv_values(dotenv_path)

        source = os.environ if env is None else env

        def lookup(name: str, default: str = "") -> str:
            value = env_file_vars.get(name) or source.get(name) or default
            return str(value)

        config_file = lookup("LLM_CONFIG_FILE").strip()
        default_model = lookup("LLM_DEFAULT_MODEL", "default").strip()
        return cls(
            proxy_url=lookup("REGISTRY_URL").strip() or None,
            config_file=Path(config_file).expanduser() if config_file else None,
            default_model=default_model or "default",
            debug_log_messages=_env_flag(lookup("LLM_DEBUG_LOG_MESSAGES")),
            enable_mlflow_tracing=_env_flag(lookup("ENABLE_MLFLOW_TRACING")),
        )

    def with_api_key(self, api_key: str | None) -> "LLMConfig":
        """Return a shallow copy with an A2A-provided API key attached."""
        clone = LLMConfig(
            proxy_url=self.proxy_url,
            config_file=self.config_file,
            default_model=self.default_model,
            debug_log_messages=self.debug_log_messages,
            enable_mlflow_tracing=self.enable_mlflow_tracing,
            app_name=self.app_name,
            mlflow_trace_tags=dict(self.mlflow_trace_tags),
            api_key=str(api_key).strip() if api_key else None,
            timeout=self.timeout,
        )
        clone._fallback_models_cache = self._fallback_models_cache
        return clone

    def with_trace_options(
        self,
        *,
        app_name: str | None = None,
        trace_tags: Mapping[str, Any] | None = None,
    ) -> "LLMConfig":
        """Return a shallow copy with additional MLflow trace metadata."""
        tags = dict(self.mlflow_trace_tags)
        if trace_tags:
            tags.update(
                {str(key): str(value) for key, value in trace_tags.items() if value is not None}
            )
        clone = LLMConfig(
            proxy_url=self.proxy_url,
            config_file=self.config_file,
            default_model=self.default_model,
            debug_log_messages=self.debug_log_messages,
            enable_mlflow_tracing=self.enable_mlflow_tracing,
            app_name=str(app_name).strip() if app_name else self.app_name,
            mlflow_trace_tags=tags,
            api_key=self.api_key,
            timeout=self.timeout,
        )
        clone._fallback_models_cache = self._fallback_models_cache
        return clone

    def load_fallback_models(self) -> dict[str, FallbackModelConfig]:
        """Load LiteLLM YAML fallback aliases from ``config_file``."""
        if self._fallback_models_cache is not None:
            return dict(self._fallback_models_cache)
        if self.config_file is None:
            self._fallback_models_cache = {}
            return {}
        if not self.config_file.exists():
            raise FileNotFoundError(f"LLM_CONFIG_FILE does not exist: {self.config_file}")

        yaml = cast(Any, importlib.import_module("yaml"))
        with self.config_file.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, dict):
            raise ValueError("LLM_CONFIG_FILE must contain a YAML mapping")

        model_list = payload.get("model_list", [])
        if not isinstance(model_list, list):
            raise ValueError("LLM_CONFIG_FILE model_list must be a list")

        models: dict[str, FallbackModelConfig] = {}
        for entry in model_list:
            if not isinstance(entry, dict):
                continue
            alias = str(entry.get("model_name", "")).strip()
            if not alias:
                continue
            raw_params = entry.get("litellm_params") or {}
            if not isinstance(raw_params, dict):
                raise ValueError(f"LLM fallback alias {alias!r} litellm_params must be a mapping")
            params = _resolve_env_references(dict(raw_params))
            if not isinstance(params, dict):
                raise ValueError(f"LLM fallback alias {alias!r} litellm_params must be a mapping")
            provider_model = str(params.get("model", "")).strip()
            if not provider_model:
                raise ValueError(f"LLM fallback alias {alias!r} is missing litellm_params.model")
            models[alias] = FallbackModelConfig(
                alias=alias,
                provider_model=provider_model,
                litellm_params={str(key): value for key, value in params.items()},
            )

        self._fallback_models_cache = models
        return dict(models)
