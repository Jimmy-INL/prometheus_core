import importlib.util
from pathlib import Path


def _load_add_markings():
    path = Path(__file__).resolve().parents[2] / "scripts" / "add_markings.py"
    spec = importlib.util.spec_from_file_location("add_markings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = _load_add_markings()


def test_python_marking_goes_on_top():
    out = m.add_marking('"""Doc."""\nimport os\n', "#")
    assert out.startswith("# This file is part of Prometheus\n")
    assert '# SPDX-License-Identifier: MIT\n\n"""Doc."""\nimport os\n' in out
    assert "#\n" in out  # blank marking lines carry no trailing space


def test_shebang_and_encoding_stay_first():
    src = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nprint(1)\n"
    out = m.add_marking(src, "#")
    lines = out.splitlines()
    assert lines[:3] == ["#!/usr/bin/env python3", "# -*- coding: utf-8 -*-", "# This file is part of Prometheus"]
    assert out.endswith("\nprint(1)\n")


def test_typescript_uses_line_comments():
    out = m.add_marking("import x from 'y'\n", "//")
    assert out.startswith("// This file is part of Prometheus\n")
    assert "\n//\n" in out
    assert out.endswith("// SPDX-License-Identifier: MIT\n\nimport x from 'y'\n")


def test_idempotent():
    once = m.add_marking("#!/usr/bin/env python3\nprint(1)\n", "#")
    assert m.add_marking(once, "#") == once
    assert m.is_marked(once)


def test_empty_file_gets_marking_only():
    assert m.add_marking("", "#") == m.render("#")
