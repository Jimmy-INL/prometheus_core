# 005 — LLM configuration and aliases

status: implemented
sources: README.md, docs/ENV_SETUP.md, llm_config.example.yaml, prometheus_api/llm_client/config.py, prometheus_api/llm_client/client.py, prometheus_api/llm_client/exceptions.py, tests/test_llm_client.py
depends-on: none

## Purpose
Let applications select LLM models through stable aliases while supporting LiteLLM proxy discovery and local YAML fallback configuration.

## Requirements
- REQ-005-01: `LLMConfig.from_env(...)` MUST load `REGISTRY_URL`, `LLM_CONFIG_FILE`, `LLM_DEFAULT_MODEL`, `LLM_DEBUG_LOG_MESSAGES`, and `ENABLE_MLFLOW_TRACING`.
- REQ-005-02: When no explicit env mapping is supplied, `LLMConfig.from_env(...)` MUST load a `.env` file from the current working directory if present.
- REQ-005-03: `LLMConfig.from_env(...)` MUST trim string values, convert truthy flag strings from `1`, `true`, `yes`, or `on`, and default the chat alias to `default`.
- REQ-005-04: `LLMConfig.with_api_key(...)` MUST return a shallow copy with a stripped transient API key and preserve the loaded fallback model cache.
- REQ-005-05: `LLMConfig.with_trace_options(...)` MUST merge trace tags, stringify non-null tag values, update `app_name` only when provided, and preserve the fallback model cache.
- REQ-005-06: `load_fallback_models()` MUST return an empty mapping when no `config_file` is set and MUST raise `FileNotFoundError` when a configured file does not exist. ⚠ untested
- REQ-005-07: Fallback YAML MUST be a mapping with a list-shaped `model_list`; each valid entry MUST expose `model_name` and `litellm_params.model`.
- REQ-005-08: Fallback YAML parsing MUST resolve `os.environ/NAME` references when environment variables are available and MUST cache parsed aliases.
- REQ-005-09: Proxy alias discovery MUST read `/v1/models`, accept aliases from `id`, `model_name`, or `model`, deduplicate them, sort them, and cache them.
- REQ-005-10: `list_models()` MUST prefer proxy aliases when `REGISTRY_URL` is reachable and fall back to YAML aliases only when the proxy is unreachable.
- REQ-005-11: Missing aliases MUST raise `LLMAliasError` with the missing alias, available aliases, and an instruction to configure LiteLLM or `LLM_CONFIG_FILE`.
- REQ-005-12: `resolve_model(alias)` MUST return the alias itself on the proxy path and the provider model name on the fallback path.

## Behavior
- BEH-005-01: GIVEN `LLM_DEFAULT_MODEL=medium` WHEN `LLMClient()` is called without `model` THEN chat uses alias `medium`.
- BEH-005-02: GIVEN a reachable proxy that lacks `default` WHEN default chat is requested THEN `LLMAliasError` lists the proxy aliases and does not consult fallback YAML.
- BEH-005-03: GIVEN a proxy connection error WHEN aliases are listed THEN fallback YAML aliases are returned if configured.

## Interfaces
- `FallbackModelConfig(alias: str, provider_model: str, litellm_params: dict[str, Any])`
- `LLMConfig(proxy_url: str | None = None, config_file: Path | None = None, default_model: str = "default", debug_log_messages: bool = False, enable_mlflow_tracing: bool = False, app_name: str | None = None, mlflow_trace_tags: dict[str, str] = {}, api_key: str | None = None, timeout: float = 30.0)`
- `LLMConfig.from_env(env: Mapping[str, str] | None = None, env_file: Path | None = None) -> LLMConfig`
- `LLMConfig.with_api_key(api_key: str | None) -> LLMConfig`
- `LLMConfig.with_trace_options(app_name: str | None = None, trace_tags: Mapping[str, Any] | None = None) -> LLMConfig`
- `LLMConfig.load_fallback_models() -> dict[str, FallbackModelConfig]`
- `LLMClientError`
- `LLMAliasError`

## Constraints
- The proxy is the primary production path; fallback YAML is a local/degraded path used only when proxy discovery or calls fail with request-level unavailability.
- `llm_config.example.yaml` is the tracked template; developer-specific `llm_config.yaml` files must remain untracked.
- Alias names are deployment configuration, not provider model names, on the proxy path.

## Out of scope / Non-goals
- This package does not choose provider-specific model names beyond reading configured aliases.
- This spec does not require proxy aliases to match fallback aliases.

## Open questions
- Error cases for malformed fallback YAML are enforced in code but not all have direct regression tests.
- Proxy alias cache invalidation is not exposed; a long-lived client will keep the first discovered alias set.
