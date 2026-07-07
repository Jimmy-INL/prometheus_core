# Prometheus API Specs Index

This directory is the spec-driven-development contract for `prometheus_api`.
Specs describe required behavior that future changes must preserve or update.

## Architecture in 10 lines
- `prometheus_api.storage_client` wraps [DeepLynx](../docs/DEPENDENCIES.md#deeplynx) HTTP APIs behind typed sync and async clients.
- `ConnectionConfig` centralizes DeepLynx org/project, auth, data source, timeout, retry, and SSL settings.
- Storage resource classes own endpoint contracts for items, tags, search, files, relationships, and timeseries data.
- `DeepLynxFileSystem` exposes DeepLynx file records as an `fsspec` `deeplynx://` filesystem.
- `prometheus_api.llm_client` routes chat and embedding calls through [LiteLLM](../docs/DEPENDENCIES.md#litellm) proxy aliases with YAML fallback.
- LLM normalization, secret redaction, [A2A](../docs/DEPENDENCIES.md#agent2agent-a2a) credential extraction, and optional [MLflow](../docs/DEPENDENCIES.md#mlflow) tracing sit behind provider-agnostic response models.
- `prometheus_api.agent` lets specialist agents subclass `PrometheusAgent` while the base handles A2A execution, app wiring, auth, and registry registration.
- Agent helpers emit status updates, input-required messages, worker-thread progress, and native A2A artifacts.
- `prometheus_api.contract` and `prometheus_api.a2a_stream` define dependency-light frontend/client-agent payload and stream handling.
- Redis helpers persist task, artifact, and context state when available and degrade to process-local memory when unavailable.

## Specs

| NNN | Name | Status | Summary |
| --- | --- | --- | --- |
| 001 | Storage configuration and authentication | implemented | DeepLynx connection settings, auth headers, retries, and storage client lifecycle. |
| 002 | Storage items, tags, search, and pagination | implemented | Item CRUD, tag resolution, search APIs, model parsing, and sync/async parity. |
| 003 | Storage files, relationships, and timeseries | implemented | File upload/download, chunked uploads, relationship APIs, and timeseries calls. |
| 004 | DeepLynx fsspec filesystem | implemented | `deeplynx://` path semantics, metadata versioning, lookup fallbacks, and deletion. |
| 005 | LLM configuration and aliases | implemented | Environment config, fallback YAML parsing, proxy alias discovery, and alias errors. |
| 006 | LLM chat and embeddings | implemented | Sync/async chat and embedding calls, proxy/fallback execution, and response shaping. |
| 007 | LLM security and tracing | implemented | Secret redaction, A2A-provided API keys, prompt-safe debug logging, and MLflow tracing. |
| 008 | Agent app, card, auth, and registry | implemented | Agent card loading, workflow injection, Starlette routes, bearer auth, and LiteLLM registration. |
| 009 | Agent execution, events, and workers | implemented | Executor lifecycle, heartbeats, status/background events, cancellation, and blocking worker support. |
| 010 | Agent artifacts, input, and context state | implemented | Input-required payloads, artifact cataloging/resolution, DeepLynx artifact upload, and context state. |
| 011 | A2A conversation contract and streams | implemented | Frontend/client-agent payload models plus NDJSON/SSE stream accumulation. |
| 012 | Redis-backed state and degradation | implemented | Shared Redis client creation and Redis-backed A2A task storage with memory fallback. |
| 013 | Package distribution and developer commands | implemented | Package metadata, version export, Makefile quality gates, install smoke tests, and container build contract. |

## Interface Ownership

Each public interface should be claimed by exactly one spec:

- Storage exports and resources: 001-004.
- LLM exports: 005-007.
- Agent exports and routes: 008-010, 012.
- Top-level contract, stream helpers, and Redis helpers: 011-012.
- Package metadata, Makefile commands, and container packaging: 013.

## How Agents Use These Specs

- Implementing: pick REQ IDs, write or extend tests that encode them, then code until green. Reference IDs in the commit message.
- Extending: add new REQ/BEH entries using the next free number before coding; update `status` when done.
- Auditing / drift check: walk each REQ, locate the enforcing test or code; report `satisfied / violated / untested / obsolete` per ID. Propose spec edits for intentional drift, code fixes for unintentional drift.
