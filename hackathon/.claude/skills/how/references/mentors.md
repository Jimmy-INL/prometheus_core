# Mentors and help

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

## Topic → mentor

From deck 01, slide 4. Ask early (deck 02, slide 17). When you are not sure, ask any mentor in the room.

| your problem is about | ask |
|---|---|
| The stack, Docker, the backend, the UI, login, signing keys, the orchestrator, discovery | Daniel Schwen, Brandon Biggs |
| `PrometheusAgent`, `_execute`, helpers, input-required, long work, registration | Daniel Schwen |
| `LLMClient`, flavors, profiles, LLM keys, `LLMAliasError` | Brandon Biggs |
| DeepLynx, uploads, a plot that does not render | Isaac Huffman |
| The card, skill design, workflows, tests, the Day 1 and Day 2 agents | Mengnan Li, Mauricio Tano, Zach Prince |
| Git, the PR, your team | Chris Rubel |
| Access to `github.inl.gov/genesis` (team `open`), the PAT, the registry login | Any mentor, now |

Chat: Teams. Bugs: JIRA `PPLT`. Read docs at the pin, not the docs site: `gh api "repos/genesis/prometheus_api/contents/docs/agent/GUIDE.md?ref=95c32b5" --hostname github.inl.gov -H "Accept: application/vnd.github.raw"`.
Say what you ran, expected, and got, with the error line. Never paste a key or an `.env`.
