"""Secret redaction and A2A LLM credential extraction helpers."""

from __future__ import annotations

import re
from typing import Any

from google.protobuf.json_format import MessageToDict

SECRET_FIELD_FRAGMENTS = (
    "api_key",
    "llm_api_key",
    "authorization",
    "token",
    "secret",
    "password",
)
REDACTED = "[REDACTED]"

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api_key|llm_api_key|authorization|token|secret|password)\b"
    r"(\s*[:=]\s*)([^,\s;]+)"
)


def _is_secret_key(key: Any) -> bool:
    normalized = str(key).strip().lower()
    return any(fragment in normalized for fragment in SECRET_FIELD_FRAGMENTS)


def redact_secrets(value: Any) -> Any:
    """Recursively redact common secret-bearing fields from debug payloads."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = REDACTED if _is_secret_key(key_text) else redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", value)
    return value


def _llm_api_key_from_data(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    provided_inputs = data.get("provided_inputs")
    if isinstance(provided_inputs, dict):
        value = provided_inputs.get("llm_api_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = data.get("llm_api_key")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def extract_llm_api_key_from_a2a_context(context: Any) -> str | None:
    """Read ``llm_api_key`` only from structured A2A v1 data parts."""
    message = getattr(context, "message", None)
    if message is None:
        return None

    for part in getattr(message, "parts", []) or []:
        if part.WhichOneof("content") != "data":
            continue
        api_key = _llm_api_key_from_data(MessageToDict(part.data))
        if api_key:
            return api_key
    return None
