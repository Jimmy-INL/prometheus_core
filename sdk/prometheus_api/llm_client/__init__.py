"""Provider-agnostic LLM client utilities built on LiteLLM."""

from .client import AsyncLLMClient, LLMClient
from .config import FallbackModelConfig, LLMConfig
from .exceptions import LLMAliasError, LLMClientError
from .models import ChatResponse, EmbeddingResponse
from .normalization import normalize_embedding_input, normalize_messages
from .security import extract_llm_api_key_from_a2a_context, redact_secrets
from .tracing import AMSC_API_KEY_ENV, enable_amsc_x_api_key

__all__ = [
    "AsyncLLMClient",
    "ChatResponse",
    "EmbeddingResponse",
    "FallbackModelConfig",
    "LLMAliasError",
    "LLMClient",
    "LLMClientError",
    "LLMConfig",
    "AMSC_API_KEY_ENV",
    "enable_amsc_x_api_key",
    "extract_llm_api_key_from_a2a_context",
    "normalize_embedding_input",
    "normalize_messages",
    "redact_secrets",
]
