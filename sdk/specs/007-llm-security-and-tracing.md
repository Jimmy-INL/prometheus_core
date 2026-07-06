# 007 — LLM security and tracing

status: implemented
sources: README.md, docs/ENV_SETUP.md, prometheus_api/llm_client/security.py, prometheus_api/llm_client/tracing.py, prometheus_api/llm_client/client.py, tests/test_llm_client.py
depends-on: 005, 006

## Purpose
Keep LLM usage safe for agents and operators by redacting secrets, accepting transient A2A LLM keys only from structured data, and making MLflow tracing opt-in.

## Requirements
- REQ-007-01: `redact_secrets(...)` MUST recursively redact dict fields whose names contain common secret fragments including `api_key`, `llm_api_key`, `authorization`, `token`, `secret`, and `password`.
- REQ-007-02: `redact_secrets(...)` MUST redact secret assignment patterns inside strings while preserving non-secret values.
- REQ-007-03: A2A LLM API key extraction MUST read only structured `DataPart` payloads, including `provided_inputs.llm_api_key` or top-level `llm_api_key`, and MUST ignore visible text parts.
- REQ-007-04: `LLMClient.from_a2a_context(...)` and `AsyncLLMClient.from_a2a_context(...)` MUST attach an extracted structured API key to a copied config.
- REQ-007-05: Proxy requests MUST send `Authorization: Bearer <key>` when a transient config key or per-call `api_key` is provided.
- REQ-007-06: Debug logging MUST hide prompt and embedding content by default while still logging metadata such as alias, path, counts, roles, provider model, usage, and latency.
- REQ-007-07: When `debug_log_messages=True`, debug logging MAY include normalized prompt/embedding content only after secret redaction.
- REQ-007-08: MLflow MUST NOT be imported or configured when `ENABLE_MLFLOW_TRACING` is false.
- REQ-007-09: When tracing is enabled, setup MUST load `.env`, import MLflow, set `MLFLOW_EXPERIMENT_NAME` when present, enable `mlflow.litellm.autolog()`, and run setup only once.
- REQ-007-10: `enable_amsc_x_api_key()` MUST inject `AM_SC_API_KEY` as `X-Api-Key` into MLflow REST calls and warn when the env var is absent.
- REQ-007-11: Chat tracing MUST create spans named `llm_client.chat`, record model alias/provider/path/client attributes, record messages as inputs, and set normalized response data as outputs.
- REQ-007-12: Trace tags `app_name`, `base_url`, and `model` MUST be protected and override caller-supplied tags.

## Behavior
- GIVEN visible text containing `llm_api_key` and a structured DataPart key WHEN an A2A client is created THEN only the structured key is used. (id: BEH-007-01)
- GIVEN debug logging without opt-in message logging WHEN a prompt contains sensitive content THEN logs include counts/roles but not prompt text. (id: BEH-007-02)
- GIVEN tracing with caller tags that conflict with protected tags WHEN chat runs THEN protected `app_name`, `base_url`, and `model` values win. (id: BEH-007-03)

## Interfaces
- `redact_secrets(value: Any) -> Any`
- `extract_llm_api_key_from_a2a_context(context: Any) -> str | None`
- `AMSC_API_KEY_ENV = "AM_SC_API_KEY"`
- `enable_amsc_x_api_key() -> None`
- `setup_mlflow_tracing() -> Any`
- `chat_trace(enabled: bool, tags: Mapping[str, str], attributes: Mapping[str, Any], inputs: Mapping[str, Any]) -> Iterator[Any | None]`
- `LLMClient.from_a2a_context(context: Any, config: LLMConfig | None = None, **kwargs) -> LLMClient`
- `AsyncLLMClient.from_a2a_context(context: Any, config: LLMConfig | None = None, **kwargs) -> AsyncLLMClient`

## Constraints
- MLflow tracing remains opt-in because traces can record chat inputs and outputs.
- Structured A2A `llm_api_key` values are transient runtime credentials and MUST NOT be parsed from plain text or logged unredacted.
- `AM_SC_API_KEY` is specific to MLflow REST authentication and is not a model-provider API key.

## Out of scope / Non-goals
- This package does not redact arbitrary semantic secrets outside the configured field fragments and assignment pattern.
- This package does not provide a persistent credential store for A2A-provided LLM keys.

## Open questions
- Redaction is pattern-based and may miss provider-specific secret field names that do not contain the configured fragments.
- Tracing support depends on the installed MLflow version exposing `mlflow.litellm` and `mlflow.entities.SpanType`.
