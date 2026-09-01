import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import setup_agent  # noqa: E402


def test_create_agent_copies_prompt_and_workflow_template_dirs(tmp_path, monkeypatch):
    output_dir = tmp_path / "generated-agent"
    monkeypatch.setattr(setup_agent, "PLATFORM_ENV_PATH", tmp_path / "missing-platform.env")

    setup_agent.create_agent(
        {
            "TEMPLATE_NAME": "Demo Agent",
            "TEMPLATE_DESCRIPTION": "A demo generated agent",
            "TEMPLATE_SLUG": "demo-agent",
            "TEMPLATE_CLASS": "Demo",
            "TEMPLATE_SKILL_ID": "demo_analysis",
            "TEMPLATE_SKILL_NAME": "Demo Analysis",
            "TEMPLATE_SKILL_DESCRIPTION": "Runs demo analysis",
            "OUTPUT_DIR": str(output_dir),
            "TRIM_COMMENTS": "false",
        }
    )

    assert (output_dir / "prompts" / "README.md").is_file()
    assert (output_dir / "prompts" / "system_prompt.txt").is_file()
    assert (output_dir / "workflows" / "README.md").is_file()
    workflow_example = output_dir / "workflows" / "example_workflow.yaml.example"
    assert workflow_example.is_file()
    assert "id: demo-agent.example_workflow" in workflow_example.read_text(encoding="utf-8")
    assert "skill_id: demo_analysis" in workflow_example.read_text(encoding="utf-8")

    dockerfile = (output_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY prompts /app/prompts" in dockerfile
    assert "COPY workflows /app/workflows" in dockerfile

    agent_py = (output_dir / "agent.py").read_text(encoding="utf-8")
    assert "from prometheus_api import load_prompt" in agent_py
    assert "PROMPTS_DIR" not in agent_py
    assert "def load_prompt(" not in agent_py
    assert "add_http_endpoint" in agent_py
    assert "add_static_endpoint" in agent_py


def test_select_platform_env_values_includes_identity_verification_keys(tmp_path):
    """USER_IDENTITY_PUBLIC_KEY/ISS/AUD must be copied from the platform .env --
    a scaffolded agent should be able to verify platform users out of the box,
    without the developer having to hunt these down manually. The private key
    must NEVER be selected: this agent verifies, it never mints."""
    platform_env = tmp_path / "platform.env"
    platform_env.write_text(
        "AGENT_SECRET=shared-secret\n"
        "REDIS_PASSWORD=redis-pw\n"
        "LITELLM_MASTER_KEY=sk-litellm\n"
        "USER_IDENTITY_PRIVATE_KEY=should-never-be-copied\n"
        "USER_IDENTITY_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----abc-----END PUBLIC KEY-----\n"
        "USER_IDENTITY_ISS=prometheus-platform\n"
        "USER_IDENTITY_AUD=prometheus-agents\n"
        "DEEPLYNX_ORG_ID=42\n",
        encoding="utf-8",
    )

    selected = setup_agent.select_platform_env_values(platform_env)

    assert selected["USER_IDENTITY_PUBLIC_KEY"] == "-----BEGIN PUBLIC KEY-----abc-----END PUBLIC KEY-----"
    assert selected["USER_IDENTITY_ISS"] == "prometheus-platform"
    assert selected["USER_IDENTITY_AUD"] == "prometheus-agents"
    assert "USER_IDENTITY_PRIVATE_KEY" not in selected
    assert selected["DEEPLYNX_ORG_ID"] == "42"
