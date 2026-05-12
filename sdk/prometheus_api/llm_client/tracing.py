"""Optional MLflow tracing helpers for LLM chat calls."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .exceptions import LLMClientError

logger = logging.getLogger("prometheus_api.llm_client")

AMSC_API_KEY_ENV = "AM_SC_API_KEY"

_MLFLOW_SETUP_DONE = False


def enable_amsc_x_api_key() -> None:
    """
    Inject X-Api-Key into all MLflow REST calls.
    """
    import mlflow.utils.rest_utils as rest_utils  # type: ignore[import-not-found]

    api_key = os.environ.get(AMSC_API_KEY_ENV)

    if not api_key:
        logger.warning("Warning: %s not found in environment.", AMSC_API_KEY_ENV)

    original_http_request = rest_utils.http_request

    def patched_http_request(host_creds, endpoint, method, *args, **kwargs):
        headers = dict(kwargs.get("headers") or kwargs.get("extra_headers") or {})
        headers["X-Api-Key"] = api_key

        if "headers" in kwargs:
            kwargs["headers"] = headers
        else:
            kwargs["extra_headers"] = headers

        return original_http_request(host_creds, endpoint, method, *args, **kwargs)

    rest_utils.http_request = patched_http_request


def _import_mlflow() -> Any:
    try:
        return importlib.import_module("mlflow")
    except ImportError as exc:
        raise LLMClientError(
            "MLflow tracing is enabled but the 'mlflow' package is not installed. "
            "Install mlflow or unset ENABLE_MLFLOW_TRACING."
        ) from exc


def _mlflow_litellm() -> Any:
    try:
        return importlib.import_module("mlflow.litellm")
    except ImportError as exc:
        mlflow = _import_mlflow()
        litellm_module = getattr(mlflow, "litellm", None)
        if litellm_module is None:
            raise LLMClientError("MLflow tracing requires mlflow.litellm support.") from exc
        return litellm_module


def _span_type_chain() -> Any:
    try:
        entities = importlib.import_module("mlflow.entities")
    except ImportError as exc:
        raise LLMClientError("MLflow tracing requires mlflow.entities.SpanType.") from exc
    return entities.SpanType.CHAIN


def _load_default_dotenv() -> None:
    dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.exists():
        return
    dotenv = importlib.import_module("dotenv")
    dotenv.load_dotenv(dotenv_path, override=False)


def setup_mlflow_tracing() -> Any:
    """Initialize MLflow tracing once and return the imported MLflow module."""
    global _MLFLOW_SETUP_DONE

    _load_default_dotenv()
    mlflow = _import_mlflow()
    if _MLFLOW_SETUP_DONE:
        return mlflow

    logging.getLogger("mlflow.tracing.export.async_export_queue").setLevel(logging.WARNING)
    enable_amsc_x_api_key()

    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME")
    if experiment_name:
        mlflow.set_experiment(experiment_name)

    _mlflow_litellm().autolog()
    _MLFLOW_SETUP_DONE = True
    return mlflow


@contextmanager
def chat_trace(
    *,
    enabled: bool,
    tags: Mapping[str, str],
    attributes: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> Iterator[Any | None]:
    """Create an MLflow chat span when tracing is enabled."""
    if not enabled:
        yield None
        return

    mlflow = setup_mlflow_tracing()
    with mlflow.tracing.context(tags=dict(tags)):
        with mlflow.start_span(
            name="llm_client.chat",
            span_type=_span_type_chain(),
            attributes=dict(attributes),
        ) as span:
            span.set_inputs(dict(inputs))
            yield span
