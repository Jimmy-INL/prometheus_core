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
    assert "PROMPTS_DIR" in agent_py
    assert "add_http_endpoint" in agent_py
    assert "add_static_endpoint" in agent_py
