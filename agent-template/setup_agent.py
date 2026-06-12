#!/usr/bin/env python3
"""
Agent Template Setup Script

This script creates a new agent from the template by replacing all template
placeholders with your custom values.

Usage:
    python setup_agent.py <agent_name> [output_directory]

Example:
    python setup_agent.py "Plant Analysis" ./plant-agent
    python setup_agent.py "Data Validator"
"""

import re
import shutil
import sys
from pathlib import Path


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    # Replace spaces and special chars with underscores
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text.lower()


def to_pascal_case(text: str) -> str:
    """Convert text to PascalCase."""
    # Remove special characters except spaces and hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    # Split on spaces and hyphens, capitalize each word
    words = re.split(r"[-\s]+", text)
    return "".join(word.capitalize() for word in words if word)


def to_kebab_case(text: str) -> str:
    """Convert text to kebab-case."""
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.lower()


def get_user_input(prompt: str, default: str = "") -> str:
    """Get user input with optional default value."""
    if default:
        response = input(f"{prompt} [{default}]: ").strip()
        return response if response else default
    return input(f"{prompt}: ").strip()


def collect_agent_info() -> dict[str, str]:
    """Interactively collect agent information from the user."""
    print("\n" + "=" * 70)
    print("  Agent Template Setup")
    print("=" * 70)
    print("\nThis script will help you create a new agent from the template.")
    print("Please provide the following information:\n")

    # Get agent name
    while True:
        agent_name = get_user_input("Agent name (e.g., 'Plant Analysis', 'Data Validator')")
        if agent_name:
            break
        print("Error: Agent name is required.\n")

    # Generate default values
    default_slug = to_kebab_case(agent_name)
    default_class = to_pascal_case(agent_name)

    # Get description
    description = get_user_input(
        "\nAgent description (brief summary of what it does)", f"A specialized agent for {agent_name.lower()}"
    )

    # Get slug (for directories, files, etc.)
    slug = get_user_input("\nAgent slug (used for directories and Docker)", default_slug)

    # Get class name
    class_name = get_user_input(
        "\nAgent class name (PascalCase, without an 'Agent' suffix — it is appended automatically)",
        default_class,
    )

    # Get skill information
    print("\n" + "-" * 70)
    print("  Primary Skill Configuration")
    print("-" * 70)

    skill_id = get_user_input("\nPrimary skill ID (snake_case)", f"{to_snake_case(agent_name)}_analysis")

    skill_name = get_user_input("\nPrimary skill name", f"{agent_name} Analysis")

    skill_description = get_user_input("\nPrimary skill description", f"Performs analysis using {agent_name.lower()}")

    # Get output directory
    default_output = f"./{slug}"
    output_dir = get_user_input("\nOutput directory", default_output)

    # Keep comments in the copied agent.py
    trim_comments = get_user_input(prompt="\nTrim agent.py comments", default="False")

    # Confirm
    print("\n" + "=" * 70)
    print("  Configuration Summary")
    print("=" * 70)
    print(f"\nAgent Name:        {agent_name}")
    print(f"Description:       {description}")
    print(f"Slug:              {slug}")
    print(f"Class Name:        {class_name}")
    print(f"Primary Skill ID:  {skill_id}")
    print(f"Primary Skill:     {skill_name}")
    print(f"Output Directory:  {output_dir}")
    print(f"Trim Comments:     {trim_comments}")
    print()

    confirm = get_user_input("Proceed with these settings? (yes/no)", "yes")
    if confirm.lower() not in ["yes", "y"]:
        print("\nSetup cancelled.")
        sys.exit(0)

    return {
        "TEMPLATE_NAME": agent_name,
        "TEMPLATE_DESCRIPTION": description,
        "TEMPLATE_SLUG": slug,
        "TEMPLATE_CLASS": class_name,
        "TEMPLATE_SKILL_ID": skill_id,
        "TEMPLATE_SKILL_NAME": skill_name,
        "TEMPLATE_SKILL_DESCRIPTION": skill_description,
        "OUTPUT_DIR": output_dir,
        "TRIM_COMMENTS": trim_comments,
    }


def strip_comments(content: str) -> str:
    """Remove comment lines and inline comments from Python source, then collapse excess blank lines."""
    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.lstrip()
        # Remove full-line comments (but keep shebangs)
        if stripped.startswith("#") and not stripped.startswith("#!"):
            continue
        # Remove inline comments (naive but sufficient for template code)
        code_part = line.split(" #")[0].rstrip() if " #" in line else line
        result.append(code_part)

    # Collapse runs of 3+ blank lines down to 2
    collapsed = []
    blank_count = 0
    for line in result:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                collapsed.append(line)
        else:
            blank_count = 0
            collapsed.append(line)

    return "\n".join(collapsed) + "\n"


def replace_placeholders(content: str, replacements: dict[str, str]) -> str:
    """Replace all template placeholders in content."""
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def process_file(file_path: Path, replacements: dict[str, str], output_dir: Path) -> None:
    """Process a single file, replacing placeholders."""
    # Read the file
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Replace placeholders
    new_content = replace_placeholders(content, replacements)

    # Determine output path
    relative_path = file_path.relative_to(Path(__file__).parent / "agent_template")
    output_path = output_dir / relative_path

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  ✓ {relative_path}")


def create_agent(replacements: dict[str, str]) -> None:
    """Create a new agent from the template."""
    template_dir = Path(__file__).parent / "agent_template"
    output_dir = Path(replacements["OUTPUT_DIR"])

    # Check if template exists
    if not template_dir.exists():
        print(f"\nError: Template directory '{template_dir}' not found.")
        sys.exit(1)

    # Check if output directory already exists
    if output_dir.exists():
        overwrite = get_user_input(
            f"\nWarning: Directory '{output_dir}' already exists.\n"
            f"Overwriting DELETES everything in it, including any code you have written. Overwrite? (yes/no)",
            "no",
        )
        if overwrite.lower() not in ["yes", "y"]:
            print("\nSetup cancelled.")
            sys.exit(0)
        shutil.rmtree(output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nCreating agent in '{output_dir}'...")
    print()

    # Process all files in template
    for file_path in template_dir.rglob("*"):
        # Skip directories, hidden files, and Python cache files
        if not file_path.is_file():
            continue
        if file_path.name != ".env.example" and file_path.name.startswith("."):
            continue
        if "__pycache__" in file_path.parts:
            continue
        if file_path.suffix in [".pyc", ".pyo", ".pyd", ".so", ".dll"]:
            continue

        process_file(file_path, replacements, output_dir)

    # Strip comments from agent.py if requested
    if replacements["TRIM_COMMENTS"].strip().lower() in {"true", "yes", "y", "1"}:
        agent_py = output_dir / "agent.py"
        if agent_py.exists():
            with open(agent_py, encoding="utf-8") as f:
                content = f.read()
            with open(agent_py, "w", encoding="utf-8") as f:
                f.write(strip_comments(content))
            print("  ✓ Trimmed comments from agent.py")

    print()
    message_file = Path(__file__).parent / "success_message.txt"
    with open(message_file, encoding="utf-8") as f:
        message = f.read().format(output_dir=output_dir, slug=replacements["TEMPLATE_SLUG"])
    print(message)


def main():
    """Main entry point."""
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print(__doc__)
        sys.exit(0)

    # Collect agent information
    replacements = collect_agent_info()

    # Create the agent
    create_agent(replacements)


if __name__ == "__main__":
    main()
