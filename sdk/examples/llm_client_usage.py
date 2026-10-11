# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Provider-agnostic LLMClient usage examples.

Run with the default LiteLLM registry profile:

    REGISTRY_URL=http://localhost:4000 uv run python examples/llm_client_usage.py

Or an installed direct-provider profile:

    LLM_CONFIG_PROFILE=openai OPENAI_API_KEY=... uv run python examples/llm_client_usage.py
"""

from __future__ import annotations

from prometheus_api.llm_client import LLMAliasError, LLMClient, LLMConfig


def print_setup_help() -> None:
    """Print local configuration guidance."""
    print("\nLocal setup:")
    print("  1. Use the default registry profile:")
    print("     export REGISTRY_URL=http://localhost:4000")
    print("  2. Or select an installed provider profile:")
    print("     export LLM_CONFIG_PROFILE=openai")
    print("  3. Export provider keys referenced by the selected YAML:")
    print("     export OPENAI_API_KEY=...")
    print("     export ANTHROPIC_API_KEY=...")


def example_list_models(llm: LLMClient) -> None:
    """Show configured aliases."""
    print("=== Available LLM aliases ===")
    aliases = llm.list_models()
    if not aliases:
        print("No aliases found.")
        return
    for alias in aliases:
        print(f"  - {alias}")


def example_default_chat(llm: LLMClient) -> None:
    """Call the configured default model alias."""
    print("\n=== Default chat ===")
    response = llm("Summarize this DeepLynx record in one sentence.")
    print(f"Alias: {response.model_alias}")
    print(f"Provider model: {response.provider_model}")
    print(f"Text: {response.text}")


def example_explicit_alias(llm: LLMClient) -> None:
    """Call an explicit generic alias with OpenAI-style messages."""
    print("\n=== Explicit medium alias ===")
    response = llm.medium(
        [
            {"role": "system", "content": "You are a concise engineering analyst."},
            {
                "role": "user",
                "content": "List two possible causes for a rising bearing temperature trend.",
            },
        ],
    )
    print(f"Alias: {response.model_alias}")
    print(f"Usage: {response.usage}")
    print(response.text)


def example_embeddings(llm: LLMClient) -> None:
    """Create one or more embedding vectors."""
    print("\n=== Embeddings ===")
    response = llm.embedding(["pressure spike", "temperature drift"])
    print(f"Alias: {response.model_alias}")
    print(f"Vector count: {len(response.embeddings)}")
    if response.embeddings:
        print(f"First vector dimensions: {len(response.embeddings[0])}")


def main() -> None:
    """Run all LLMClient examples."""
    print("=" * 60)
    print("LLMClient Examples")
    print("=" * 60)

    config = LLMConfig.from_env()
    print(f"Proxy URL: {config.proxy_url or '(direct provider)'}")
    print(f"LLM config: {config.config_file}")

    try:
        with LLMClient(config) as llm:
            example_list_models(llm)
            example_default_chat(llm)
            example_explicit_alias(llm)
            example_embeddings(llm)
    except LLMAliasError as exc:
        print(f"\nAlias configuration error:\n{exc}")
        print_setup_help()
    except Exception as exc:
        print(f"\nLLM call failed: {exc}")
        print_setup_help()


if __name__ == "__main__":
    main()
