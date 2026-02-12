#!/usr/bin/env python3
"""
Agent Template Setup Script

This script creates a new agent from the template by replacing all template
placeholders with your custom values.

Usage:
    python setup_agent.py <agent_name> [output_directory]

Example:
    python setup_agent.py "Weather Analysis" ./weather-agent
    python setup_agent.py "Data Validator"
"""

import os
import sys
import shutil
import re
import json
from pathlib import Path
from typing import Dict


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    # Replace spaces and special chars with underscores
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text.lower()


def to_pascal_case(text: str) -> str:
    """Convert text to PascalCase."""
    # Remove special characters except spaces and hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    # Split on spaces and hyphens, capitalize each word
    words = re.split(r'[-\s]+', text)
    return ''.join(word.capitalize() for word in words if word)


def to_kebab_case(text: str) -> str:
    """Convert text to kebab-case."""
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.lower()


def get_user_input(prompt: str, default: str = "") -> str:
    """Get user input with optional default value."""
    if default:
        response = input(f"{prompt} [{default}]: ").strip()
        return response if response else default
    return input(f"{prompt}: ").strip()


def collect_agent_info() -> Dict[str, str]:
    """Interactively collect agent information from the user."""
    print("\n" + "="*70)
    print("  Agent Template Setup")
    print("="*70)
    print("\nThis script will help you create a new agent from the template.")
    print("Please provide the following information:\n")

    # Get agent name
    while True:
        agent_name = get_user_input("Agent name (e.g., 'Weather Analysis', 'Data Validator')")
        if agent_name:
            break
        print("Error: Agent name is required.\n")

    # Generate default values
    default_slug = to_kebab_case(agent_name)
    default_class = to_pascal_case(agent_name)

    # Get description
    description = get_user_input(
        "\nAgent description (brief summary of what it does)",
        f"A specialized agent for {agent_name.lower()}"
    )

    # Get slug (for directories, files, etc.)
    slug = get_user_input(
        "\nAgent slug (used for directories and Docker)",
        default_slug
    )

    # Get class name
    class_name = get_user_input(
        "\nAgent class name (PascalCase)",
        default_class
    )

    # Get skill information
    print("\n" + "-"*70)
    print("  Primary Skill Configuration")
    print("-"*70)

    skill_id = get_user_input(
        "\nPrimary skill ID (snake_case)",
        f"{to_snake_case(agent_name)}_analysis"
    )

    skill_name = get_user_input(
        "\nPrimary skill name",
        f"{agent_name} Analysis"
    )

    skill_description = get_user_input(
        "\nPrimary skill description",
        f"Performs analysis using {agent_name.lower()}"
    )

    # Get output directory
    default_output = f"./{slug}"
    output_dir = get_user_input(
        "\nOutput directory",
        default_output
    )

    # Confirm
    print("\n" + "="*70)
    print("  Configuration Summary")
    print("="*70)
    print(f"\nAgent Name:        {agent_name}")
    print(f"Description:       {description}")
    print(f"Slug:              {slug}")
    print(f"Class Name:        {class_name}")
    print(f"Primary Skill ID:  {skill_id}")
    print(f"Primary Skill:     {skill_name}")
    print(f"Output Directory:  {output_dir}")
    print()

    confirm = get_user_input("Proceed with these settings? (yes/no)", "yes")
    if confirm.lower() not in ['yes', 'y']:
        print("\nSetup cancelled.")
        sys.exit(0)

    return {
        'TEMPLATE_NAME': agent_name,
        'TEMPLATE_DESCRIPTION': description,
        'TEMPLATE_SLUG': slug,
        'TEMPLATE_CLASS': class_name,
        'TEMPLATE_SKILL_ID': skill_id,
        'TEMPLATE_SKILL_NAME': skill_name,
        'TEMPLATE_SKILL_DESCRIPTION': skill_description,
        'OUTPUT_DIR': output_dir
    }


def replace_placeholders(content: str, replacements: Dict[str, str]) -> str:
    """Replace all template placeholders in content."""
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def process_file(file_path: Path, replacements: Dict[str, str], output_dir: Path) -> None:
    """Process a single file, replacing placeholders."""
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace placeholders
    new_content = replace_placeholders(content, replacements)

    # Determine output path
    relative_path = file_path.relative_to(Path('agent_template'))
    output_path = output_dir / relative_path

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"  ✓ {relative_path}")


def create_agent(replacements: Dict[str, str]) -> None:
    """Create a new agent from the template."""
    template_dir = Path('agent_template')
    output_dir = Path(replacements['OUTPUT_DIR'])

    # Check if template exists
    if not template_dir.exists():
        print(f"\nError: Template directory '{template_dir}' not found.")
        print("Make sure you're running this script from the project root.")
        sys.exit(1)

    # Check if output directory already exists
    if output_dir.exists():
        overwrite = get_user_input(
            f"\nWarning: Directory '{output_dir}' already exists. Overwrite? (yes/no)",
            "no"
        )
        if overwrite.lower() not in ['yes', 'y']:
            print("\nSetup cancelled.")
            sys.exit(0)
        shutil.rmtree(output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nCreating agent in '{output_dir}'...")
    print()

    # Process all files in template
    for file_path in template_dir.rglob('*'):
        if file_path.is_file() and not file_path.name.startswith('.'):
            process_file(file_path, replacements, output_dir)

    print()
    print("="*70)
    print("  Agent Created Successfully!")
    print("="*70)
    print(f"\nYour new agent has been created in: {output_dir}")
    print("\nNext steps:")
    print(f"  1. cd {output_dir}")
    print("  2. cp .env.example .env")
    print("  3. Edit .env if needed")
    print("  4. Install dependencies: pip install -r requirements.txt")
    print("  5. Run the agent: python agent.py")
    print("\nOr use Docker:")
    print(f"  1. docker build -t {replacements['TEMPLATE_SLUG']} {output_dir}")
    print(f"  2. docker run -p 8000:8000 --env-file {output_dir}/.env {replacements['TEMPLATE_SLUG']}")
    print(f"     (or pass env vars: docker run -p 8000:8000 -e AGENT_PORT=8000 {replacements['TEMPLATE_SLUG']})")
    print("\nFor more information, see the README.md in your agent directory.")
    print()


def main():
    """Main entry point."""
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        print(__doc__)
        sys.exit(0)

    # Collect agent information
    replacements = collect_agent_info()

    # Create the agent
    create_agent(replacements)


if __name__ == '__main__':
    main()
