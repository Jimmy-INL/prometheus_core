#!/usr/bin/env python3
"""Create or complete the platform .env from .env.example.

1. Copy .env.example to .env if .env does not exist.
2. For every variable in .env.example whose comment block carries a
   ``python3 -c "..."`` one-liner, fill a blank value in .env by running it.
   Values that are already set are never touched.
3. Exit non-zero if the API key for the selected LLM_CONFIG_PROFILE is blank.

Standard library only, so it runs before anything else is installed. Run from
anywhere; paths resolve relative to this file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
ENV = ROOT / ".env"

ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
ONE_LINER = re.compile(r'^#\s*python3 -c "(.+)"\s*$')

# LLM_CONFIG_PROFILE -> the provider key that profile cannot start without.
PROFILE_KEYS = {
    "registry": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "inl_hpc": "INL_HPC_API_KEY",
    "inl_litellm": "INL_LITELLM_API_KEY",
    "amsc": "AMSC_I2_API_KEY",
    "anl_asksage": "ASKSAGE_API_KEY",
}


def generators(example: str) -> dict[str, str]:
    """Map each variable to the one-liner in the comment block directly above it."""
    found: dict[str, str] = {}
    pending: str | None = None
    for line in example.splitlines():
        if m := ONE_LINER.match(line):
            pending = m.group(1)
        elif m := ASSIGNMENT.match(line):
            if pending:
                found[m.group(1)] = pending
            pending = None
        elif not line.startswith("#"):
            pending = None
    return found


def values(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for line in text.splitlines() if (m := ASSIGNMENT.match(line))}


def fill_secrets(text: str, gens: dict[str, str]) -> tuple[str, list[str]]:
    current = values(text)
    filled = []
    for var, code in gens.items():
        if current.get(var, ""):
            continue
        secret = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
        if var in current:
            text = re.sub(rf"^{var}=.*$", lambda _: f"{var}={secret}", text, count=1, flags=re.M)
        else:
            text = text.rstrip("\n") + f"\n{var}={secret}\n"
        filled.append(var)
    return text, filled


def missing_llm_key(env: dict[str, str]) -> str | None:
    """The blank provider key required by the selected profile, if any."""
    if env.get("LLM_CONFIG_FILE"):
        return None  # a custom YAML decides which keys it needs
    key = PROFILE_KEYS.get(env.get("LLM_CONFIG_PROFILE") or "registry")
    return key if key and not env.get(key) else None


def main() -> int:
    if not ENV.exists():
        shutil.copyfile(EXAMPLE, ENV)
        print(f"Created {ENV.name} from {EXAMPLE.name}.")

    text, filled = fill_secrets(ENV.read_text(), generators(EXAMPLE.read_text()))
    if filled:
        ENV.write_text(text)
        print(f"Generated in {ENV.name}: {', '.join(filled)}")

    env = values(text)
    if key := missing_llm_key(env):
        profile = env.get("LLM_CONFIG_PROFILE") or "registry"
        print(
            f"\n[ERROR] {key} is empty in {ENV}.\n"
            f"        LLM_CONFIG_PROFILE={profile} needs it; set it (or pick another profile)\n"
            f"        and run make again. See README.md, 'Choose an LLM profile'.\n",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
