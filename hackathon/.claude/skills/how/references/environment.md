# Environment: prerequisites, .env files, and the base image

Facts as of `prometheus_api` 95c32b5 (v0.13.0) and `prometheus_platform` `dev` 22fed42, 2026-10-05. When the code disagrees with this file, the code is correct.

The laptop needs (deck 01, slide 15; deck 03, slide 14; each has a check in `checks.md`): Docker
with Compose 2.20+ (`docker`), make, git, openssl, uv and Python 3.12 (`tools`), read access to
`github.inl.gov/genesis` (`repo-access`), a `read:packages` PAT and `docker login` on the INL
network (`registry-login`), and an LLM key (`llm-key`). Keep the three clones side by side.

## Fill the platform .env

`cp .env.example .env` in the platform folder. Required (deck 03, slide 16): `ANTHROPIC_API_KEY`,
`AGENT_SECRET`, `REDIS_PASSWORD`, `BACKEND_JWT_SECRET` (the backend stops while it is empty or
`change-me…`), `LITELLM_MASTER_KEY`, `LITELLM_DB_PASSWORD`, `ADMIN_DB_PASSWORD`. Keep
`REDIS_URL` and `LITELLM_LOCAL_PORT=9977` as they are; leave `ADMIN_DB_ENCRYPTION_KEY` empty
(`make up` writes it, `Makefile:268-281`). Fill every placeholder without printing a value, in
the platform folder:

```sh
python3 - <<'EOF'
import pathlib, secrets
p = pathlib.Path(".env")
keys = {"AGENT_SECRET", "REDIS_PASSWORD", "LITELLM_MASTER_KEY", "LITELLM_DB_PASSWORD", "ADMIN_DB_PASSWORD", "BACKEND_JWT_SECRET"}
lines = [(k + "=" + secrets.token_hex(32)) if (k := l.partition("=")[0]) in keys and l.partition("=")[1] and (not l.partition("=")[2] or l.partition("=")[2].startswith("change-me")) else l for l in p.read_text().splitlines()]
p.write_text("\n".join(lines) + "\n"); print("placeholders replaced")
EOF
```

Two traps: `ADMIN_DB_PASSWORD` is fixed at the first start (a change gives `password
authentication failed for user "admin"`; restore it, or `make down-v`). A new value makes the
agent copy stale: run `agent-env-sync`, then `make up` in the agent folder.

## The base image

Every Python service builds `FROM containers.github.inl.gov/genesis/prometheus_api:<tag>`, which
holds `prometheus_api`, `a2a-sdk` 1.x, starlette, and uvicorn (deck 02, A5): never list them in
`pyproject.toml`. Tags are short commit SHAs. `95c32b5` is v0.13.0; never pin lower.

## The pin rule

1. An uncommented, non-empty `PROMETHEUS_API_BASE_IMAGE_HASH=` line in the platform `.env` wins.
2. Else the Makefile value counts: `PROMETHEUS_API_BASE_IMAGE_HASH ?= 95c32b5` (`Makefile:22`).

An empty line sets the variable to empty, so `?=` does nothing and every `FROM` gets an empty tag:
"invalid reference format". A plain `docker compose up` breaks the same way: always use `make`.
The agent template defaults to `latest` (`agent_template/docker-compose.yml:8`), so put
`PROMETHEUS_API_BASE_IMAGE_HASH=<pin>` into the agent `.env` (`base-image-pin`, `agent-base-image`).

## Your agent's .env

`setup_agent.py` copies `AGENT_SECRET`, `REDIS_PASSWORD`, `LITELLM_MASTER_KEY`,
`USER_IDENTITY_PUBLIC_KEY`, `USER_IDENTITY_ISS`, `USER_IDENTITY_AUD`, `LLM_CONFIG_PROFILE`, and
`DEEPLYNX_*` (`setup_agent.py:22-36`). Add the pin, the key of the agent's profile (and forward it
under `environment:`, template issue #17), and `USER_IDENTITY_REQUIRED=false` only when the
platform sets it. After each edit, `make up` in the agent folder.

## First login and the signing key

Open http://localhost:5150 and complete the setup wizard (the first user is admin). Then Admin ›
Signing Keys: generate, then activate. Without an active key every turn fails with "No
'userToken' found…" (deck 03, slide 5 and A9; `admin-user`, `signing-key`). Never commit or paste a
`.env`. This repository ignores `.env*`; check with `git check-ignore -v <agent>/.env`.
