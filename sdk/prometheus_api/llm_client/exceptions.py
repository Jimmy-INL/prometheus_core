"""Exceptions raised by the provider-agnostic LLM client."""


class LLMClientError(RuntimeError):
    """Base error for LLM client failures."""


class LLMAliasError(ValueError):
    """Raised when a configured model alias is unavailable."""


class LLMToolCallError(LLMClientError):
    """Raised when an LLM tool-call response does not satisfy the caller's contract."""
