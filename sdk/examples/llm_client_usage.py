"""Provider-agnostic LLMClient usage examples.

Run with either a LiteLLM proxy:

    LITELLM_URL=http://localhost:4000 uv run python examples/llm_client_usage.py

Or a local fallback config:

    cp llm_config.example.yaml llm_config.yaml
    LLM_CONFIG_FILE=./llm_config.yaml uv run python examples/llm_client_usage.py
"""

from __future__ import annotations

from prometheus_api.llm_client import LLMAliasError, LLMClient, LLMConfig


def print_setup_help() -> None:
    """Print local configuration guidance."""
    print("\nLocal setup:")
    print("  1. Prefer a LiteLLM proxy:")
    print("     export LITELLM_URL=http://localhost:4000")
    print("  2. Or use a fallback config:")
    print("     cp llm_config.example.yaml llm_config.yaml")
    print("     export LLM_CONFIG_FILE=./llm_config.yaml")
    print("  3. Export provider keys referenced by your fallback YAML:")
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
        temperature=0,
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
    print(f"LITELLM_URL: {config.proxy_url or '(not set)'}")
    print(f"LLM_CONFIG_FILE: {config.config_file or '(not set)'}")
    print(f"LLM_DEFAULT_MODEL: {config.default_model}")

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
