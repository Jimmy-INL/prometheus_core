---
name: diagnose
description: Finds and fixes what does not work for a Prometheus hackathon agent or the local platform, and explains why. It works out what is needed - fix an error or a symptom (a stack that won't start, an agent missing from /agents or never called, HTTP 401, LLMAliasError, "No 'userToken' found", ModuleNotFoundError, uploads, plots, DeepLynx), check that the laptop is ready (the homework checklist - tools, GitHub, Docker and the registry login, platform health, login, the LLM key, DeepLynx, shadowing personal skills, the agent .env), or rebuild one chat turn from Valkey and the logs (each LLM step, the skills called, the exact arguments, the results, the end state). Use for "diagnose", "it doesn't work", "debug this error", a pasted error, "is my laptop ready", "homework check", "check my setup", "trace my last chat", "why wasn't my agent called", or "what arguments did it send".
argument-hint: "[what is wrong, an error, or a conversation id]"
allowed-tools:
  - Bash(docker restart *-agent)
  - Bash(docker restart client-agent)
  - "Bash(docker exec client-agent python -c \"import os, urllib.request as u; r=u.Request('http://localhost:8000/discovery/refresh', method='POST', headers={'Authorization':'Bearer '+os.environ['AGENT_SECRET']}); print(u.urlopen(r).read())\")"
---

# /diagnose

Find why something does not work, explain the cause, and fix it. The argument: `$ARGUMENTS`

## Setup

1. Run `git rev-parse --show-toplevel` (`<root>`). A KB file name means a file in
   `<root>/.claude/skills/how/references/`. Read `conventions.md`, `teaching.md`, `checks.md`, `troubleshooting.md`.
2. Find the platform, the template, and the user's agent as `conventions.md` says ("Find the
   folders", "Find your agent"). Ask once for a missing path (header `Path`; add "Not cloned yet"
   for a setup check). Note `<agent>` and `<container>` (`grep -m1 'container_name:' <agent>/docker-compose.yml`).
   No agent: skip the agent checks, and say so.
3. Read the ports: `grep -E '^(BACKEND_PORT|LITELLM_LOCAL_PORT|FRONTEND_DEV_PORT|FRONTEND_PROD_PORT|REDIS_LOCAL_PORT)=' <platform>/.env`.

## Rules

- Never print, ask for, or accept a secret (`conventions.md`; "Secrets in these commands" in
  `checks.md`); a pasted one must be rotated. Use only the KB commands. Evidence is a status, a
  code, a count, a name, or a filtered log line. Ask only for decisions and the user's own steps.
- Read the platform and the template with read-only Bash. Never edit a tracked platform file,
  `.claude/`, `~/.claude/`, or another participant's folder.

## Fix kinds (`checks.md`)

1. **Safe**: apply it, then explain it in one or two lines. Before `docker restart`, run
   `activity`; when it shows a recent line, say what the restart stops and ask (header
   `Restart`). Restart only `<container>` or `client-agent`, never a platform agent. Run `make up`
   only as `cd <agent> && test -f agent_card.json && make up`, then wait for the registration:
   `for i in $(seq 15); do docker logs --since 1m <container> 2>&1 | grep -q "Registered '" && break; sleep 2; done; docker logs --since 1m <container> 2>&1 | grep -E "Registered '|Registry registration attempt" | tail -n 2`.
   After a card or code change, run `discovery-refresh`.
2. **Yes**: show the exact change (key names only for an `.env`; a diff and "Before a write" for
   an agent file), then ask (header `Fix`): "Apply the fix" (recommended, say why), "Show me the
   steps", "Skip". A platform `make up` or `make restart` empties the registry: `make down` in the
   agent folder, the target (timeout 10 minutes), then `make up` there. Before `make down-v`,
   state the loss (`conventions.md`).
3. **You**: give the steps, then ask (header `Done?`): "Done, check again", "Skip".

## Decide what to do

Pick the task yourself from the request and the state; do not ask the user to name it.

| when | file |
|---|---|
| an error or a symptom (a stack that won't start, an agent missing from `/agents`, a 401, `LLMAliasError`, uploads, plots, DeepLynx) | `fix-problem.md` |
| the laptop, the homework, or the setup; or Day 1 has not started and no agent exists | `check-setup.md` |
| what the orchestrator did, why the agent was not called, which arguments it sent; or a conversation id | `trace-turn.md` |

No request: run `stack-ps`. Platform down or no agent: check the setup. A status history from the
last 15 minutes (the list command of `trace-turn.md`): ask (header `Problem`): "Something broke
(Recommended)", "Explain my last chat turn", "Check my whole setup".

Read the file in this folder and obey it; "the argument" is the request. Move on when the
evidence says so: checks that pass for "never called" or "wrong arguments" go on with
`trace-turn.md`; a trace that ends in a failure goes on with `fix-problem.md`. When the cause is
the card, offer `/create-agent improve my card`.
