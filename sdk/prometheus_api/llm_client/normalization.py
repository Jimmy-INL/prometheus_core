"""Input normalization helpers for chat and embedding calls."""

from __future__ import annotations

from typing import Any

ChatMessage = dict[str, Any]
ChatInput = str | list[dict[str, Any]]
EmbeddingInput = str | list[str]


def normalize_messages(value: ChatInput) -> list[ChatMessage]:
    """Normalize a raw prompt or OpenAI-style messages into a message list."""
    if isinstance(value, str):
        stripped_text = value.strip()
        if not stripped_text:
            raise ValueError("LLM prompt text cannot be empty")
        return [{"role": "user", "content": value}]

    if not isinstance(value, list):
        raise TypeError("LLM chat input must be a string or a list of message dictionaries")
    if not value:
        raise ValueError("LLM message list cannot be empty")

    messages: list[ChatMessage] = []
    for index, message in enumerate(value):
        if not isinstance(message, dict):
            raise TypeError(f"LLM message at index {index} must be a dictionary")
        if "role" not in message or "content" not in message:
            raise ValueError(f"LLM message at index {index} must include role and content")
        role = str(message.get("role", "")).strip()
        if not role:
            raise ValueError(f"LLM message at index {index} role cannot be empty")
        content = message.get("content")
        if content is None:
            raise ValueError(f"LLM message at index {index} content cannot be None")
        if isinstance(content, str) and not content.strip():
            raise ValueError(f"LLM message at index {index} content cannot be empty")
        messages.append(dict(message))
    return messages


def normalize_embedding_input(value: EmbeddingInput) -> tuple[list[str], bool]:
    """Normalize one embedding string or a list of strings.

    Returns the normalized list and whether the caller supplied a single string.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("LLM embedding text cannot be empty")
        return [value], True

    if not isinstance(value, list):
        raise TypeError("LLM embedding input must be a string or a list of strings")
    if not value:
        raise ValueError("LLM embedding input list cannot be empty")

    texts: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"LLM embedding input at index {index} must be a string")
        if not item.strip():
            raise ValueError(f"LLM embedding input at index {index} cannot be empty")
        texts.append(item)
    return texts, False
