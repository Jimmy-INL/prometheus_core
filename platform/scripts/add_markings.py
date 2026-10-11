#!/usr/bin/env python3
"""Add the Prometheus copyright/license marking to every tracked source file.

Python files get a ``#`` comment block, TypeScript/JSX files a ``//`` block.
A shebang or encoding line stays on top; the marking goes right below it.
Files that already carry the marking are left alone, so reruns are no-ops.

    add_markings.py           # add the marking where it is missing
    add_markings.py --check   # list unmarked files, exit 1 if there are any

Standard library only. Run from anywhere inside the repository.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

MARKING = """\
This file is part of Prometheus
https://inl.gov/super-intelligence/prometheus/

Copyright 2026 Battelle Energy Alliance, LLC
All rights reserved, see NOTICE.txt for full restrictions
https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt

Licensed under the MIT License, please see LICENSE for details
https://github.com/idaholab/prometheus_core/blob/main/LICENSE

SPDX-License-Identifier: MIT
"""

# File suffix -> line comment prefix.
COMMENT = {".py": "#", ".ts": "//", ".tsx": "//", ".jsx": "//"}

# Generated or third-party files that keep their own (or no) header.
EXCLUDE = [
    "*.d.ts",
    "*/node_modules/*",
    "*/dist/*",
]

# The first line of the marking identifies an already-marked file.
SENTINEL = MARKING.splitlines()[0]


def render(prefix: str) -> str:
    return "".join(f"{prefix} {line}".rstrip() + "\n" for line in MARKING.splitlines())


def is_marked(text: str) -> bool:
    return SENTINEL in "\n".join(text.splitlines()[:5])


def add_marking(text: str, prefix: str) -> str:
    """Return ``text`` with the marking inserted after any shebang/encoding lines."""
    if is_marked(text):
        return text
    lines = text.splitlines(keepends=True)
    keep = 0
    if lines and lines[0].startswith("#!"):
        keep = 1
    if prefix == "#" and len(lines) > keep and "coding" in lines[keep] and lines[keep].startswith("#"):
        keep += 1
    head, rest = "".join(lines[:keep]), "".join(lines[keep:])
    body = render(prefix)
    if rest.strip():
        body += "\n" + rest
    return head + body


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True)
    files = []
    for name in out.stdout.splitlines():
        if Path(name).suffix not in COMMENT:
            continue
        if any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(f"/{name}", pattern) for pattern in EXCLUDE):
            continue
        if (root / name).is_file():
            files.append(root / name)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report unmarked files instead of fixing them")
    args = parser.parse_args(argv)

    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )

    unmarked = []
    for path in tracked_files(root):
        text = path.read_text(encoding="utf-8")
        if is_marked(text):
            continue
        unmarked.append(path.relative_to(root))
        if not args.check:
            path.write_text(add_marking(text, COMMENT[path.suffix]), encoding="utf-8")

    for path in unmarked:
        print(path)
    if args.check and unmarked:
        print(f"{len(unmarked)} file(s) lack the marking; run platform/scripts/add_markings.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
