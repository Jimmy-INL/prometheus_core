"""Paths for LLM configuration profiles installed with prometheus-api."""

from __future__ import annotations

from pathlib import Path


LLM_CONFIG_PROFILES = (
    "registry",
    "inl_hpc",
    "inl_litellm",
    "amsc",
    "anthropic",
    "openai",
    "anl_asksage",
)


def get_llm_config_path(profile: str = "registry") -> Path:
    """Return the installed YAML path for a named LLM configuration profile."""
    normalized = str(profile).strip().lower().removesuffix(".yaml").replace("-", "_")
    if normalized not in LLM_CONFIG_PROFILES:
        available = ", ".join(LLM_CONFIG_PROFILES)
        raise ValueError(
            f"Unknown LLM config profile {profile!r}. Available profiles: {available}."
        )

    config_path = Path(__file__).resolve().parent / f"{normalized}.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"Installed LLM config profile is missing: {config_path}")
    return config_path


__all__ = ["LLM_CONFIG_PROFILES", "get_llm_config_path"]
