"""Enforce provider-agnostic LLM usage in runtime agents."""

from pathlib import Path


FORBIDDEN_RUNTIME_PATTERNS = (
    "from anthropic import",
    "import anthropic",
    "from openai import",
    "import openai",
    "langchain_anthropic",
    "ChatAnthropic",
    "AsyncAnthropic",
    "AsyncOpenAI",
    "ANTHROPIC_API_KEY =",
    "MODEL_NAME =",
)


def _runtime_agent_files(platform_root: Path):
    for path in (platform_root / "agents").rglob("*.py"):
        if "tests" not in path.parts and ".venv" not in path.parts:
            yield path


def test_runtime_agents_do_not_use_provider_sdks(project_root):
    violations = []
    for path in _runtime_agent_files(project_root):
        source = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_RUNTIME_PATTERNS:
            if pattern in source:
                violations.append(f"{path.relative_to(project_root)}: {pattern}")

    assert not violations, "Direct provider usage remains:\n" + "\n".join(violations)


def test_agent_dependencies_do_not_install_provider_sdks(project_root):
    violations = []
    for path in (project_root / "agents").rglob("pyproject.toml"):
        source = path.read_text(encoding="utf-8").lower()
        for dependency in ('"anthropic', '"langchain-anthropic'):
            if dependency in source:
                violations.append(f"{path.relative_to(project_root)}: {dependency}")

    assert not violations, "Provider dependencies remain:\n" + "\n".join(violations)


def test_agent_compose_files_do_not_receive_provider_configuration(project_root):
    violations = []
    for path in (project_root / "agents").rglob("docker-compose.yml"):
        source = path.read_text(encoding="utf-8")
        for pattern in ("ANTHROPIC_API_KEY", "MODEL_NAME", "ANTHROPIC_BASE_URL"):
            if pattern in source:
                violations.append(f"{path.relative_to(project_root)}: {pattern}")

    assert not violations, "Provider configuration remains on agents:\n" + "\n".join(violations)
