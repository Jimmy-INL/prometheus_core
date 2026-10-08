# Calling an LLM

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

Your code picks a flavor (`small`, `medium`, `large`, `vision`, `embedding`, `default`). The `.env` profile
picks the model behind it (deck 04, slides 14-15). Import no provider SDK and hard-code no model ID.

```python
cfg = LLMConfig.from_env()  # from prometheus_api.llm_client import LLMConfig
if cfg.proxy_url:  # only the platform's LiteLLM proxy
    cfg = cfg.with_api_key(os.getenv("LITELLM_MASTER_KEY"))
async with self.llm_client(context, config=cfg) as llm:
    r = await llm.medium(prompt, max_tokens=1800)
return {"summary": r.text}
```

Source: `prometheus_platform/agents/synthesis-agent/agent.py:61-69` (not its `try`/`except`). The `if`
avoids a 401 from the proxy or the provider.

**Flavors under registry:** the platform defines only `medium` (`prometheus_platform/litellm_config.yaml:6-10`).
Another flavor raises `LLMAliasError: LLM alias 'small' is not available. Available aliases: medium.` Use
`medium` (deck 04 slides use `small`). List them:

```sh
set -a; source <platform>/.env; set +a; curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:9977/v1/models | python3 -c 'import json,sys; print(sorted(m["id"] for m in json.load(sys.stdin)["data"]))'
```

**Structured answer** (deck 04, slide 16; `prometheus_api/prometheus_api/llm_client/tools.py:335-352`):

```python
PICK = ToolDefinition.from_pydantic("pick_table", Pick, description="Choose the matching table")
async with self.llm_client(context, config=cfg) as llm:
    call = await acall_tool(llm, prompt, tool=PICK, model="medium")  # always pass model=
pick = Pick.model_validate(call.arguments)  # then check the range
```

## Profile to key map

`LLM_CONFIG_FILE` wins, then `LLM_CONFIG_PROFILE`, else `registry` (`llm_client/config.py:69-109`).

| profile | key in the container | template compose passes it |
|---|---|---|
| `registry` | none: the agent sends `LITELLM_MASTER_KEY` | yes |
| `inl_litellm` | `INL_LITELLM_API_KEY` | no (#17) |
| `inl_hpc` | `INL_HPC_API_KEY` | no (#17) |
| `amsc` | `AMSC_I2_API_KEY` | yes |
| `anthropic` | `ANTHROPIC_API_KEY` (+ `EMBEDDING_API_KEY`) | yes (embedding: no) |
| `openai` | `OPENAI_API_KEY` | yes |
| `anl_asksage` | not in 95c32b5: `ValueError: Unknown LLM config profile` | - |

## Template issue #17

The template compose passes only `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `AMSC_I2_API_KEY`
(`prometheus_agent_template/agent_template/docker-compose.yml:58-60`), and the scaffolder copies no
provider key. The maintainers will not fix it. For your `<KEY>`:

1. `grep -c '^<KEY>=.' .env`. When `0`, copy it: `grep '^<KEY>=' <platform>/.env >> .env`, or add it in your editor.
2. Add `<KEY>: ${<KEY>:-}` under `environment:` in the agent `docker-compose.yml`, then `make up`.
3. Check: `docker exec <slug>-agent sh -c 'test -n "$<KEY>" && echo set || echo missing'`.
