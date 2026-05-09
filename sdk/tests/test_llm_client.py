"""Tests for the provider-agnostic LLM client."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from a2a.types import DataPart, Part, TextPart

from prometheus_api.llm_client import (
    AsyncLLMClient,
    ChatResponse,
    EmbeddingResponse,
    LLMAliasError,
    LLMClient,
    LLMConfig,
    normalize_embedding_input,
    normalize_messages,
    redact_secrets,
)


def _fallback_yaml(tmp_path):
    path = tmp_path / "llm_config.yaml"
    path.write_text(
        """
model_list:
  - model_name: default
    litellm_params:
      model: openai/default-model
      api_key: os.environ/OPENAI_API_KEY
  - model_name: small
    litellm_params:
      model: openai/small-model
  - model_name: medium
    litellm_params:
      model: openai/medium-model
  - model_name: large
    litellm_params:
      model: anthropic/large-model
  - model_name: embedding
    litellm_params:
      model: openai/text-embedding-model
""".strip(),
        encoding="utf-8",
    )
    return path


def _proxy_response(request: httpx.Request, payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=request)


def _proxy_models(*aliases: str) -> dict:
    return {"data": [{"id": alias} for alias in aliases]}


def test_config_from_env(monkeypatch, tmp_path):
    config_path = tmp_path / "llm.yaml"
    env = {
        "REGISTRY_URL": " http://registry:4000 ",
        "LLM_CONFIG_FILE": str(config_path),
        "LLM_DEFAULT_MODEL": "medium",
        "LLM_DEBUG_LOG_MESSAGES": "true",
    }

    config = LLMConfig.from_env(env)

    assert config.proxy_url == "http://registry:4000"
    assert config.config_file == config_path
    assert config.default_model == "medium"
    assert config.debug_log_messages is True

    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    assert LLMConfig.from_env({}).default_model == "default"


def test_config_from_env_loads_default_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REGISTRY_URL", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "REGISTRY_URL=http://from-dotenv:4000\nLLM_DEFAULT_MODEL=large\n",
        encoding="utf-8",
    )

    config = LLMConfig.from_env()

    assert config.proxy_url == "http://from-dotenv:4000"
    assert config.default_model == "large"


def test_fallback_yaml_parsing_resolves_env_refs(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    config = LLMConfig(config_file=_fallback_yaml(tmp_path))

    models = config.load_fallback_models()

    assert sorted(models) == ["default", "embedding", "large", "medium", "small"]
    assert models["default"].provider_model == "openai/default-model"
    assert models["default"].litellm_params["api_key"] == "env-secret"


def test_local_development_example_config_parses():
    config_path = Path(__file__).resolve().parents[1] / "llm_config.example.yaml"
    config = LLMConfig(config_file=config_path)

    models = config.load_fallback_models()

    assert sorted(models) == ["default", "embedding", "large", "medium", "small", "vision"]
    assert models["default"].provider_model
    assert models["embedding"].provider_model


def test_default_alias_uses_configured_default_model():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("default", "medium"))
        requests.append(json.loads(request.content))
        return _proxy_response(
            request,
            {
                "model": "provider-medium",
                "choices": [{"message": {"content": "handled"}}],
                "usage": {"total_tokens": 4},
            },
        )

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy", default_model="medium"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client("Summarize this.")

    assert response.text == "handled"
    assert response.model_alias == "medium"
    assert requests[0]["model"] == "medium"


def test_alias_discovery_and_resolution_from_proxy():
    def handler(request: httpx.Request) -> httpx.Response:
        return _proxy_response(request, _proxy_models("small", "large"))

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.list_models() == ["large", "small"]
    assert client.resolve_model("small") == "small"


def test_missing_default_alias_error_is_actionable():
    def handler(request: httpx.Request) -> httpx.Response:
        return _proxy_response(request, _proxy_models("embedding", "large", "medium", "small"))

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LLMAliasError) as exc_info:
        client("hello")

    message = str(exc_info.value)
    assert "LLM alias 'default' is not available" in message
    assert "Available aliases: embedding, large, medium, small" in message
    assert "Configure it in LiteLLM or fallback LLM_CONFIG_FILE" in message


def test_normalize_raw_string_and_message_list():
    assert normalize_messages(" hello ") == [{"role": "user", "content": " hello "}]

    messages = [{"role": "system", "content": "Be concise."}]
    normalized = normalize_messages(messages)

    assert normalized == messages
    assert normalized is not messages


@pytest.mark.parametrize(
    "value, expected_error",
    [
        ("", ValueError),
        ([], ValueError),
        ([{"role": "user"}], ValueError),
        ([{"role": "", "content": "hello"}], ValueError),
        ([{"role": "user", "content": ""}], ValueError),
        ({"role": "user", "content": "hello"}, TypeError),
    ],
)
def test_normalize_messages_rejects_invalid_inputs(value, expected_error):
    with pytest.raises(expected_error):
        normalize_messages(value)  # type: ignore[arg-type]


def test_normalize_embedding_input():
    assert normalize_embedding_input("text") == (["text"], True)
    assert normalize_embedding_input(["a", "b"]) == (["a", "b"], False)

    with pytest.raises(ValueError):
        normalize_embedding_input("")
    with pytest.raises(ValueError):
        normalize_embedding_input([])
    with pytest.raises(TypeError):
        normalize_embedding_input([1])  # type: ignore[list-item]


def test_sync_chat_method_uses_proxy():
    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("large"))
        posted.append(json.loads(request.content))
        return _proxy_response(
            request,
            {
                "model": "resolved-large",
                "choices": [{"message": {"content": "analysis"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.large("Analyze this.", temperature=0)

    assert isinstance(response, ChatResponse)
    assert response.text == "analysis"
    assert response.model_alias == "large"
    assert response.provider_model == "resolved-large"
    assert response.usage == {"prompt_tokens": 2, "completion_tokens": 1}
    assert posted[0]["messages"] == [{"role": "user", "content": "Analyze this."}]
    assert posted[0]["temperature"] == 0


@pytest.mark.asyncio
async def test_async_chat_method_uses_proxy():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("medium"))
        return _proxy_response(
            request,
            {
                "model": "resolved-medium",
                "choices": [{"message": {"content": "async answer"}}],
                "usage": {"total_tokens": 3},
            },
        )

    client = AsyncLLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await client.medium([{"role": "user", "content": "Analyze."}])

    assert response.text == "async answer"
    assert response.model_alias == "medium"
    assert response.provider_model == "resolved-medium"
    assert response.usage == {"total_tokens": 3}
    await client.aclose()


def test_sync_embedding_method_uses_proxy():
    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("embedding"))
        posted.append(json.loads(request.content))
        return _proxy_response(
            request,
            {
                "model": "resolved-embedding",
                "data": [{"embedding": [0.1, 0.2]}],
                "usage": {"total_tokens": 2},
            },
        )

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.embedding("bearing temperature rising")

    assert isinstance(response, EmbeddingResponse)
    assert response.embeddings == [[0.1, 0.2]]
    assert response.model_alias == "embedding"
    assert response.provider_model == "resolved-embedding"
    assert posted[0]["input"] == "bearing temperature rising"


@pytest.mark.asyncio
async def test_async_embedding_method_uses_proxy():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("embedding"))
        return _proxy_response(
            request,
            {
                "model": "resolved-embedding",
                "data": [{"embedding": [1, 2]}, {"embedding": [3, 4]}],
            },
        )

    client = AsyncLLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await client.embedding(["pressure spike", "temperature drift"])

    assert response.embeddings == [[1.0, 2.0], [3.0, 4.0]]
    assert response.model_alias == "embedding"
    await client.aclose()


def test_proxy_unavailable_uses_fallback_sdk(monkeypatch, tmp_path):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("proxy down", request=request)

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return {
            "model": "openai/default-model",
            "choices": [{"message": {"content": "fallback answer"}}],
            "usage": {"total_tokens": 8},
        }

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy", config_file=_fallback_yaml(tmp_path)),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client("Fallback please.")

    assert response.text == "fallback answer"
    assert response.model_alias == "default"
    assert response.provider_model == "openai/default-model"
    assert calls[0]["model"] == "openai/default-model"
    assert calls[0]["messages"] == [{"role": "user", "content": "Fallback please."}]


@pytest.mark.asyncio
async def test_async_proxy_unavailable_uses_fallback_sdk(monkeypatch, tmp_path):
    calls: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("proxy down", request=request)

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return {
            "model": "openai/medium-model",
            "choices": [{"message": {"content": "async fallback"}}],
        }

    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    client = AsyncLLMClient(
        config=LLMConfig(proxy_url="http://proxy", config_file=_fallback_yaml(tmp_path)),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await client.medium("Fallback async.")

    assert response.text == "async fallback"
    assert calls[0]["model"] == "openai/medium-model"
    await client.aclose()


def test_reachable_proxy_rejection_does_not_fallback(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("default"))
        return _proxy_response(request, {"error": "bad request"}, status_code=400)

    def fake_completion(**kwargs):
        raise AssertionError("fallback should not be called")

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy", config_file=_fallback_yaml(tmp_path)),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client("Do not fallback.")


def test_fallback_embedding_uses_litellm_sdk(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_embedding(**kwargs):
        calls.append(kwargs)
        return {
            "model": "openai/text-embedding-model",
            "data": [{"embedding": [0, 1]}, {"embedding": [2, 3]}],
        }

    import litellm

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    client = LLMClient(config=LLMConfig(config_file=_fallback_yaml(tmp_path)))

    response = client.embedding(["a", "b"])

    assert response.embeddings == [[0.0, 1.0], [2.0, 3.0]]
    assert calls[0]["model"] == "openai/text-embedding-model"
    assert calls[0]["input"] == ["a", "b"]


def test_debug_logging_hides_prompt_content_by_default(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("default"))
        return _proxy_response(
            request,
            {
                "model": "resolved-default",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 3},
            },
        )

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with caplog.at_level(logging.DEBUG, logger="prometheus_api.llm_client"):
        client("secret prompt text")

    assert "secret prompt text" not in caplog.text
    assert "message_count" in caplog.text
    assert "roles" in caplog.text
    assert "resolved-default" in caplog.text
    assert "total_tokens" in caplog.text


def test_opt_in_debug_logging_redacts_prompt_content(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("default"))
        return _proxy_response(
            request,
            {"model": "resolved-default", "choices": [{"message": {"content": "ok"}}]},
        )

    client = LLMClient(
        config=LLMConfig(proxy_url="http://proxy", debug_log_messages=True),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with caplog.at_level(logging.DEBUG, logger="prometheus_api.llm_client"):
        client("api_key=abc123")

    assert "[REDACTED]" in caplog.text
    assert "abc123" not in caplog.text


def test_secret_redaction_recurses_through_common_secret_fields():
    payload = {
        "api_key": "one",
        "nested": {"authorization": "two", "safe": "ok"},
        "items": [{"access_token": "three"}],
        "text": "password: four",
    }

    redacted = redact_secrets(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["authorization"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["items"][0]["access_token"] == "[REDACTED]"
    assert redacted["text"] == "password: [REDACTED]"


def test_async_client_extracts_llm_api_key_from_a2a_datapart_only():
    context = SimpleNamespace(
        message=SimpleNamespace(
            parts=[
                Part(root=TextPart(text='{"llm_api_key": "visible-text-secret"}')),
                Part(root=DataPart(data={"provided_inputs": {"llm_api_key": "structured-key"}})),
            ]
        )
    )

    client = AsyncLLMClient.from_a2a_context(context, config=LLMConfig())

    assert client.config.api_key == "structured-key"


def test_a2a_api_key_is_sent_as_proxy_bearer_token():
    observed_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers.append(request.headers.get("authorization"))
        if request.url.path == "/v1/models":
            return _proxy_response(request, _proxy_models("default"))
        return _proxy_response(request, {"choices": [{"message": {"content": "ok"}}]})

    context = MagicMock()
    context.message.parts = [
        Part(root=DataPart(data={"provided_inputs": {"llm_api_key": "structured-key"}}))
    ]
    client = LLMClient.from_a2a_context(
        context,
        config=LLMConfig(proxy_url="http://proxy"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client("hello")

    assert observed_headers == ["Bearer structured-key", "Bearer structured-key"]
