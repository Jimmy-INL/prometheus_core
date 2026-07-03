# Prompt Templates

Put large static LLM prompts here instead of embedding them in `agent.py`.

Example usage:

```python
from pathlib import Path

PROMPTS_DIR = Path(__file__).with_name("prompts")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = load_prompt("system_prompt.txt")
prompt = SYSTEM_PROMPT.format(input_data=params["input_data"])
```

Prompt files are ordinary source files. Keep placeholders explicit, escape
literal JSON braces as `{{` and `}}` when using `str.format`, and add tests for
important prompt formatting paths.
