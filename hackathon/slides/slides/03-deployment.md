---
title: Your Local Platform
footer: Day 1 · Your local platform
accent: dep
index:
  time: '1:45'
  heading: Your local platform
  color: var(--sky)
  blurb: What runs where, four commands and the registry-wipe trap, first login with a signing key, health checks, reference agents, which LLM flavors the platform offers, DeepLynx for files, the six likeliest problems.
---

# Your local platform {.title kicker="Day 1 · 1:45 pm" pills="All participants | 45 min | internals in the appendix"}
You started it at home. Now: what it runs for your agent, how to tell it is healthy, the LLM models it offers, DeepLynx for your files, and what to do when something is off.

---

## By the break, your platform is ready for an agent {eyebrow="Goal"}

:::: grid 4
::: card acc
<div class="kpi"><span class="v">1</span></div>

### Healthy

{.small}
All services up, and you know where to look when one isn't.
:::

::: card acc
<div class="kpi"><span class="v">2</span></div>

### Logged in

{.small}
An admin user and an active signing key.
:::

::: card acc
<div class="kpi"><span class="v">3</span></div>

### LLMs answer

{.small}
You have a key for an LLM profile.
:::

::: card acc
<div class="kpi"><span class="v">4</span></div>

### Files work

{.small}
An upload lands in DeepLynx.
:::
::::

::: callout info
Platform not starting yet? Work through the bonus slides at the end of this deck with a mentor.
:::

---

## Three addresses you need {eyebrow="What runs"}

{widths="330px||"}
| Address | What it is | You use it to… |
|---|---|---|
| `http://localhost:5150` | the chat UI | test your agent like a user {.hl} |
| `http://localhost:9977` | LiteLLM: the agent registry and the LLM gateway | see registered agents and available models |
| `http://localhost:8600` | the backend | check health (`/healthz`) |

{.body}
Behind them: the orchestrator (`client-agent`), three agents, a state store, and two databases. They talk to each other on the Docker network `prometheus_platform_agent-network`, which your agent joins too.

---

## Four commands, one trap {eyebrow="Day to day"}

:::: grid 2 gap=30px
```bash {.sm}
cd ~/prometheus/prometheus_platform/platform
make up                     # build and start
make restart                # restart, no rebuild
make logs SERVICE=client-agent
make down                   # stop
```

|||

::: callout bad
**Every `make up` or `make restart` empties the agent registry.** The platform's own agents re-register by themselves. **Your agent doesn't**: restart it afterwards with `docker restart <your-agent>`.
:::
::::

---

## An admin user, then a signing key {eyebrow="First login"}

::: steps
#### Open `http://localhost:5150`

{.small}
On first start a setup wizard asks for a username and password. Any local values work (not your INL login); the first user becomes admin.

#### Admin › Signing Keys → generate, then activate

{.small}
The platform signs every chat turn with it, so agents know which user is asking.

#### Type `/agents` in the chat

{.small}
You should see form-filler, OSTI research, and synthesis.
:::

::: callout warn
No active key → every chat turn fails with "No 'userToken' found…".
:::

---

## Is it healthy? {eyebrow="Health checks"}

```bash {.sm}
make ps                                     # all "Up"; most also "(healthy)"
curl -s localhost:8600/healthz              # {"status":"ok"}

set -a; source .env; set +a                 # for the key below
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     localhost:9977/v1/agents | python3 -m json.tool     # registered agents
```

:::: grid 2
::: callout
Then ask the chat something real: "Find recent OSTI papers on SiC cladding". Watch it with `make logs SERVICE=client-agent`.
:::

::: callout warn
A 401 from LiteLLM means a missing or wrong `LITELLM_MASTER_KEY` header.
:::
::::

---

## Reference agents for tomorrow {eyebrow="Learn from working code"}

```bash {.sm}
make DEBUG_AGENTS=true up        # adds the reference agents
```

{widths="330px||"}
| Agent | Shows you how to… | Try |
|---|---|---|
| `artifact-debug-agent` | publish an image through DeepLynx | "Make an image with the word Success" {.hl} |
| `corrosion-agent` | ask the user for missing inputs | "Corrosion analysis of SS316" |
| `thread-pattern-agent` | run long work in the background | "Run a background task" |

{.small}
Read them in `prometheus_platform/platform/agents/debug-agents/`. Each is a short, complete example of one platform feature.

---

## Which LLMs your agent uses {eyebrow="LLMs"}

::: cols 1.45fr 1fr
{.body}
Your code asks for a **flavor** (`small`, `medium`, `large`, `vision`, `embedding`). One line in your agent's `.env` picks a **profile**: a provider plus the model behind each flavor.

{.sm .nw}
| Profile | Provider | Key in `.env` |
|---|---|---|
| `inl_litellm` | INL LiteLLM | `INL_LITELLM_API_KEY` |
| `amsc` | American Science Cloud | `AMSC_I2_API_KEY` |
| `anl_asksage` | ANL AskSage | `ASKSAGE_API_KEY` |

{.small}
The profiles ship with the SDK in `sdk/prometheus_api/llm_configs/`, AskSage included; its embeddings use Voyage (`EMBEDDING_API_KEY`). Leave `LLM_CONFIG_PROFILE` unset and you get `registry`, which only defines `medium`: `small`, `large` and `vision` raise `LLMAliasError`. Pick one of these three.

|||

```text {.sm}
# your agent's .env: pick one
LLM_CONFIG_PROFILE=inl_litellm
INL_LITELLM_API_KEY=…

# LLM_CONFIG_PROFILE=amsc
# AMSC_I2_API_KEY=…

# LLM_CONFIG_PROFILE=anl_asksage
# ASKSAGE_API_KEY=…
```

{.small}
Then `make up` in your agent's folder. Keys stay in `.env`, never in code or the repo.
:::

Note: Assumes the template compose forwards INL_LITELLM_API_KEY, ASKSAGE_API_KEY, EMBEDDING_API_KEY and INL_HPC_API_KEY, and that LiteLLM trusts the INL certificate (registry profile). Check both before presenting.

---

## Where your files live {eyebrow="DeepLynx"}

::: flow
- [gray flex=1] **Chat upload**
- ->  {w=50}
- [teal flex=1.2] **DeepLynx** | stores the file
- ->  {w=50}
- [orange flex=1] **Your agent** | reads it, writes results back
- ->  {w=50}
- [sky flex=1] **Chat UI** | renders the plot
:::

- Every upload and every result file goes through DeepLynx, INL's data store.
- **Without it, your agent never sees uploads and a PNG cannot render.**
- Use the shared instance (`deeplynx.inl.gov`) or a local one (bonus slides). The settings are the `DEEPLYNX_*` lines in `.env`.

---

## Check that the platform can reach DeepLynx {eyebrow="DeepLynx"}

::: col
```python {.sm}
# from inside the backend container (has DEEPLYNX_* env)
docker exec -i backend python - <<'EOF'
from prometheus_api.storage_client import (
    ConnectionConfig, StorageClient)
cfg = ConnectionConfig.from_env()
with StorageClient(cfg) as c:
    page = c.items.list(page_size=5)
    print("OK", cfg.base_url, len(page.items), "items")
EOF
```

{.small}
Then upload a file in the chat. It should appear in the DeepLynx UI under your project, and `/artifacts` lists it.
:::

---

## The problems you are most likely to hit {eyebrow="Something is off"}

{.sm widths="470px|"}
| Symptom | Fix |
|---|---|
| Every chat turn fails: "No 'userToken' found…" | Admin › Signing Keys: generate and **activate** a key |
| Your agent disappeared from `/agents` | the platform restarted: `docker restart <your-agent>` |
| LLM call gets HTTP 401 | the key for your `LLM_CONFIG_PROFILE` is missing or wrong in the agent's `.env` |
| "Unknown LLM config profile" | a typo in `LLM_CONFIG_PROFILE`, or an SDK image without that profile |
| "DeepLynx storage is not configured" | set the `DEEPLYNX_*` lines, `make restart` |
| Backend fails: `password authentication failed for user "admin"` | a second platform checkout reuses the same Docker volumes: restore the old `ADMIN_DB_PASSWORD` and `ADMIN_DB_ENCRYPTION_KEY` in `.env`, or `make down-v` (deletes users and keys) |
| Something else | `make logs SERVICE=<name>`; the appendix has the full troubleshooting tables |

---

## Before the break {eyebrow="Checkpoint"}

:::: grid 2 gap=30px
{.check}
- ☐ `make ps`: all services up
- ☐ `curl localhost:8600/healthz` → `{"status":"ok"}`
- ☐ `/v1/agents` lists 4 agents (client + 3)
- ☐ Logged in, signing key active
- ☐ `/agents` in the chat works
- ☐ A question gets an LLM answer
- ☐ (optional) DeepLynx: an upload appears in the DeepLynx UI

|||

::: card acc
### Stuck?

{.body}
Raise your hand now. Mentors fix environment problems during the break, so that at 2:45 pm everyone can follow the agent session with a running stack.
:::

::: card
### Next: Building an agent (2:45 pm)

{.body}
The agent template is already in your clone (`prometheus_platform/agent-template/`). Have `uv --version` working.
:::
::::

---

# Bonus: catch-up slides {.section .bonus num="+"}
For participants whose platform does not start yet: prerequisites, clone, `.env` (with the local base image), startup failures, and a local DeepLynx.

---

## Before you clone {eyebrow="Bonus · Prerequisites"}

{widths="280px|"}
| Need | Why / check |
|---|---|
| **Docker + Compose v2** | The Makefile calls `docker compose -p prometheus_platform`. The compose files use `include:` and `additional_contexts`, so Compose ≥ 2.20 with BuildKit is needed. Check: `docker info`, `docker compose version`. |
| **GNU make, git, openssl** | `make up` generates keys with `openssl rand`. |
| **`gh`, the GitHub CLI** | Used for forks and PRs. `brew install gh` (needs admin), or copy the release binary from `github.com/cli/cli/releases` into `~/.local/bin`; then `gh auth login --hostname github.inl.gov`. |
| **The `prometheus_api` base image** | Nothing to set up: `LOCAL_SDK=true` in `.env` builds it from `sdk/` on your laptop. (With INL network access you can pull it from `containers.github.inl.gov` instead: a PAT with `read:packages`, then `docker login`.) |
| **An LLM credential** | `ANTHROPIC_API_KEY` for the bundled LiteLLM proxy, or a key for another profile (`INL_LITELLM_API_KEY`…). |
| **uv + Python 3.12** | Only for running things outside Docker: tests, a host-run agent, `setup_agent.py`. `uv --version` |
| Node.js 22 (optional) | Only to run the frontend dev server on the host (`make react-dev`). |
| Disk space | Several GB for images. No minimum RAM is documented; if builds get killed, raise the Docker Desktop memory limit. |

{.small}
Podman: the template README mentions it, but the platform Makefile only drives `docker compose`. Use Docker Desktop (or Docker Engine) for the hackathon.

---

## Clone, and where the base image comes from {eyebrow="Bonus · Step 1"}

:::: grid 2 gap=30px
```bash {.sm}
# your fork (see previous session), default branch dev
git clone git@github.inl.gov:<you>/prometheus_platform.git
cd prometheus_platform/platform     # the stack lives here
git remote add upstream \
  git@github.inl.gov:genesis/prometheus_platform.git
git switch dev

# smoke test: can you build the base image?
make -C ../sdk build-local    # → prometheus_api:local
# next step: LOCAL_SDK=true in .env, so make up
# builds every service FROM it
```

|||

::: card
#### Why a base image?

{.small}
Every Python service (backend, client-agent, all agents) is built `FROM` the `prometheus_api` image. With `LOCAL_SDK=true`, `make up` first builds it from `../sdk` as `prometheus_api:local`: no registry, no login, no VPN.
:::

::: card
#### Or pull it from the registry

{.small}
On the INL network you can skip `LOCAL_SDK` and pull the pinned image: `docker login containers.github.inl.gov` with a PAT that has `read:packages`. Docker keeps the login in your credential helper; the PAT never goes into `.env`.
:::

::: callout warn
`LOCAL_SDK=true` builds whatever is in `sdk/`, not the pin in `platform/Makefile`. After `git pull`, the next `make up` rebuilds it.
:::
::::

---

## `cp .env.example .env`: the required values {eyebrow="Bonus · Step 2 · in prometheus_platform/platform"}

:::: grid 32 gap=28px
{.sm}
| Variable | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Used by the Anthropic models in `litellm_config.yaml` (and the `anthropic` profile) |
| `AGENT_SECRET` | A2A bearer token: backend → client-agent, LiteLLM → agents |
| `REDIS_PASSWORD` | Valkey `--requirepass` |
| `REDIS_URL` | `redis://:${REDIS_PASSWORD}@redis:6379` (keep it as is) |
| `BACKEND_JWT_SECRET` | **Session-cookie signing key.** The backend won't start while it is empty or still `change-me…`. (The old `CHAINLIT_AUTH_SECRET` is no longer read.) |
| `LITELLM_MASTER_KEY` | Registry and gateway admin key (agents register with it) |
| `LITELLM_DB_PASSWORD` | litellm-db Postgres |
| `ADMIN_DB_PASSWORD` | admin-db Postgres |
| `LITELLM_LOCAL_PORT=9977` | Already set. Compose has **no default** for it, so keep the line. |
| `LOCAL_SDK=true` | Build the base image from `../sdk` instead of pulling it {.hl} |
| `ADMIN_DB_ENCRYPTION_KEY=` | Leave empty: `make up` writes a Fernet key into `.env` |

|||

#### Generate every "change-me" {.acc}

```bash {.sm}
python3 -c "import secrets; \
print(secrets.token_hex(32))"
```

{.small}
Use a different value for each secret. Anything works locally; the values only have to be consistent across the platform and your agent (`setup_agent.py` copies them for you).

::: callout bad
Never commit `.env`. Never paste it into chat or a PR. It is in `.gitignore`; `git status` should never show it.
:::
::::

---

## The stack won't start {eyebrow="Bonus · Troubleshooting · 1"}

{.sm widths="470px|"}
| Symptom | Cause → fix |
|---|---|
| `failed to resolve …prometheus_api:` (empty tag) or `invalid reference format` | Empty `PROMETHEUS_API_BASE_IMAGE_HASH`: an uncommented empty line in `.env`, or you ran `docker compose` without make. Remove the line, or set it to the value in `platform/Makefile`. |
| `unauthorized` / `denied` pulling the base image | You are pulling from the registry: set `LOCAL_SDK=true` in `.env`, or `docker login containers.github.inl.gov` with a PAT that has `read:packages` (INL network or VPN). |
| `pull access denied for prometheus_api` | `LOCAL_SDK=true` is set, but `docker compose` ran without make, so `prometheus_api:local` was never built. Run `make base-image`, or always go through `make up`. |
| `.env not found` from `check-prerequisites` | `cp .env.example .env` |
| Port is already allocated (5150, 8600, 9977, 6379) | Another process or an old stack is using it. `make down`, or change `*_PORT` in `.env`. |
| Backend exits: "jwt_secret is not configured" | `BACKEND_JWT_SECRET` is empty or still `change-me…`. Generate a value (an old `CHAINLIT_AUTH_SECRET` is no longer read). |
| Backend exits during an alembic step | Migrations run in `backend/docker-entrypoint.sh` before uvicorn; `make logs SERVICE=backend`. |
| SSL / certificate errors during `npm ci` or `pip` on the INL network | TLS inspection. `certs/INL.pem` is checked in (PR #100); pull the latest `dev`. Python images get the bundle from the base image. |
| `network … has active endpoints` on `make up` | An external agent is still attached to `prometheus_platform_agent-network`. Stop it first (`make down` in the agent dir). |
| Build killed / exit 137 | Out of memory. Raise the Docker Desktop memory limit (the OSTI agent is heavy). |
| Behind a corporate proxy: downloads time out | Set `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`. They are **build** args; add `backend,admin-db` and your agent names to `NO_PROXY`. |

---

## Clone, build, start {eyebrow="Bonus · Local DeepLynx · 1"}

:::: grid 2 gap=30px
```bash {.sm}
git clone https://github.com/idaholab/DeepLynx.git
cd DeepLynx
cp .env_sample .env
docker compose build
docker compose up          # add -d to detach
```

{.sm}
| Service | Host port | What |
|---|---|---|
| `ui` | 3000 | admin web UI (auth disabled locally) {.hl} |
| `server` | 5000 | **API** at `/api/v1`, which the platform uses {.hl} |
| `docs` | 3001 | documentation site |
| `nx-postgres` | 5432 | its database |
| `mcp` | 43656 | DeepLynx MCP server |
| `insight-*` | 5009, 5672… | only with `--profile insight` |

|||

::: card
#### It runs next to the platform

{.small}
DeepLynx has its own compose project and network (`nexus-network`). The platform containers reach it through your host at `host.docker.internal:5000`.
:::

::: callout warn
**macOS: port 5000** is often taken by the AirPlay Receiver (System Settings › General › AirDrop & Handoff). Turn it off, or remap the `server` port.
:::

::: callout warn
**Port 5432** clashes with any local Postgres. The platform's own databases do not publish ports, so they won't collide.
:::

{.small}
Pulled new DeepLynx changes? `docker compose up --build`.
::::

---

## Create a project at `http://localhost:3000` {eyebrow="Bonus · Local DeepLynx · 2"}

::: grid 3 gap=20px
<img alt="Selecting the INL default organization" class="fit" src="assets/deeplynx/dl_3.png" style="border:1px solid var(--rule); border-radius:8px"/>

{.small}
**①** Skip or take the quick tour. In the top-left dropdown, select **"INL – default organization"**.

|||

<img alt="Empty organization with + Project button" class="fit" src="assets/deeplynx/dl_4.png" style="border:1px solid var(--rule); border-radius:8px"/>

{.small}
**②** Click **"+ Project"** and give it any name. A project is a fenced-off database for the platform.

|||

<img alt="Project page with project ID in URL" class="fit" src="assets/deeplynx/dl_6.png" style="border:1px solid var(--rule); border-radius:8px"/>

{.small}
**③** The URL now shows `localhost:3000/project/1`. **1 is your project ID**; each new project gets a new one.
:::

---

## Generate an API key and point the platform at it {eyebrow="Bonus · Local DeepLynx · 3"}

::: cols 0.8fr 0.8fr 1.4fr gap=22px
<img alt="Local Developer menu with Settings" class="fit" src="assets/deeplynx/dl_7.png" style="border:1px solid var(--rule); border-radius:8px"/>

{.small}
**④** Bottom left: person icon → under *Local Developer* click **Settings** (not the organization settings in the far-left bar).

|||

<img alt="API Keys section with Generate New" class="fit" src="assets/deeplynx/dl_8.png" style="border:1px solid var(--rule); border-radius:8px"/>

{.small}
**⑤** API Keys → **"+ Generate New"**. Copy the **key and secret** now: the secret is shown only once.

|||

{.small}
**⑥** In `prometheus_platform/platform/.env`:

```text {.sm}
DEEPLYNX_KEY=…
DEEPLYNX_SECRET=…
DEEPLYNX_BASE_URL=http://host.docker.internal:5000/api/v1/
DEEPLYNX_ORG_ID=1
DEEPLYNX_PROJECT_ID=1
```

{.small}
Then `make restart`. Copy the same values into your agent's `.env` (`setup_agent.py` copies every `DEEPLYNX_*` for you).

{.small}
Agent running on the host (not in Docker)? Use `http://localhost:5000/api/v1`.
:::

---

# Appendix: reference {.section .appendix num="A"}
Reference material behind the talk. Skipped in the session; use it when you need the details.

---

## You ran the stack at home. By 2:30 pm you also… {eyebrow="Goal"}

:::: grid 2 gap=30px
::: steps
#### Know what is running

{.small}
Every container, its port, and what `make up` really does.

#### Are logged in, with a signing key

{.small}
The setup wizard's admin, plus an active key so agents accept your requests.

#### Get an answer

{.small}
`/agents` lists the agents, and a question goes through the LLM proxy.

#### Can upload a file

{.small}
It lands in DeepLynx and agents can read it.
:::

|||

::: card acc
### This session

{.sm}
1. What is running
2. Configuration and `make up`
3. The base image
4. First login and health checks
5. LLM configuration
6. DeepLynx
7. When things are off
:::

::: callout warn
Platform not starting yet? Use the **bonus slides** at the end of this deck with a mentor.
:::
::::

---

## Ports on your host {eyebrow="What you will run"}

:::: grid 2 gap=30px
| URL | Service | Variable |
|---|---|---|
| `http://localhost:5150` | Frontend (Vite dev) | `FRONTEND_DEV_PORT` {.hl} |
| `http://localhost:8080` | Frontend (nginx; `PROFILE=prod`) | `FRONTEND_PROD_PORT` |
| `http://localhost:8600` | Backend (FastAPI) | `BACKEND_PORT` |
| `http://localhost:9977` | LiteLLM: registry, gateway, proxy | `LITELLM_LOCAL_PORT` |
| `localhost:6379` | Valkey (Redis protocol) | `REDIS_LOCAL_PORT` |
| `http://localhost:8001` | client-agent (system-test mode only) | `CLIENT_AGENT_PORT` |
| `http://localhost:8008` | artifact-debug-agent (`DEBUG_AGENTS=true`) | `ARTIFACT_DEBUG_PORT` |

|||

{.body}
Everything else stays **inside** the Docker network `prometheus_platform_agent-network` and is reached by service name:

```yaml {.sm}
http://litellm:4000        # or litellm-proxy:4000
redis://redis:6379
http://backend:8000        # JWKS for agents
http://client-agent:8000
http://<agent-service>:8000
```

::: callout
A port is already taken, for example by a local Redis on 6379? Change the variable in `.env` and re-run `make up`.
:::
::::

---

## The `.env` knobs worth knowing {eyebrow="Configuration"}

::: grid 2 gap=26px
{.xs}
| Variable | Default | Purpose |
|---|---|---|
| `DEBUG_AGENTS` | `false` | Include `agents/debug-agents/*` |
| `LLM_CONFIG_PROFILE` | `registry` | Which flavor→model map agents use |
| `LLM_CONFIG_FILE` | empty | Custom YAML inside the container; overrides the profile |
| `OPENAI_API_KEY`, `INL_HPC_API_KEY`, `INL_LITELLM_API_KEY`, `AMSC_I2_API_KEY`, `EMBEDDING_API_KEY` | empty | Only what the chosen profile needs |
| `LOCAL_SDK` | `false` | `true`: build the base image from `../sdk` (`prometheus_api:local`) |
| `PROMETHEUS_API_BASE_IMAGE_HASH` | commented | Override the pin in `platform/Makefile` |
| `DEEPLYNX_BASE_URL/KEY/SECRET/ORG_ID/PROJECT_ID` | commented | Storage for uploads and `deeplynx://` |
| `PROMETHEUS_MAX_UPLOAD_BYTES` | 104857600 | 100 MiB upload cap |
| `HTTP(S)_PROXY`, `NO_PROXY` | commented | Build args for Python images only |

|||

{.xs}
| Variable | Default | Purpose |
|---|---|---|
| `USER_IDENTITY_REQUIRED` | `true` | Agents reject turns without a user JWT |
| `USER_IDENTITY_PRIVATE_KEY` | empty | Backend fallback signing key (not in JWKS) |
| `USER_IDENTITY_PUBLIC_KEY` | empty | Static key for agents *outside* compose; `JWKS_URL` wins |
| `USER_IDENTITY_ISS` / `_AUD` | prometheus-platform / -agents | JWT claims |
| `USER_IDENTITY_TTL` | 7200 | Token lifetime in seconds |
| `BACKEND_WORKERS` | 1 | uvicorn workers (sessions live in Valkey) |
| `PROMETHEUS_MESH_WORKERS` / `_TIMEOUT_SECONDS` | 2 / 120 | VTK mesh-conversion pool, per-mesh time budget |
| `BACKEND_MEM_LIMIT` | 4g | backend container memory cap |
| `BACKEND_PUBLIC_URL` | empty | Browser origin for OIDC redirects |
| `CREDENTIAL_BROKER` | `env` | `env` = global creds; `vault` = per user |
| `PROMETHEUS_SYSTEM_TESTING` | `false` | Publish the client-agent on :8001 |
:::

{.tiny}
Documented but unused on `dev`: `FRONTEND_URL`, `LOCAL_CERT_FILE`/`CERT_FILE`. OIDC is now configured in Admin › Identity Providers.

---

## `make up`, and what it really does {eyebrow="Under the hood"}

::: flow
- [gray flex=1] **check-prerequisites** | `.env` exists, docker is running
- ->  {w=30}
- [violet dash flex=1] **base-image** | if `LOCAL_SDK`: build the SDK image
- ->  {w=30}
- [sky flex=1] **generate** | writes `docker-compose.agents.yml` (`include:` of `agents/*/docker-compose.yml`)
- ->  {w=30}
- [sky flex=1] **ensure-admin-encryption-key** | Fernet key into `.env` if empty
- ->  {w=30}
- [crimson flex=1] **clear-litellm-db** | `compose down` + delete the `litellm-db-data` volume
- ->  {w=30}
- [green flex=1] **up --build -d** | profile `dev`: all services + frontend-dev
:::

:::: grid 2 gap=26px
```bash {.sm}
make up                        # build + start, detached
make LOCAL_SDK=true up         # base image from ../sdk
make up-fg                     # same, logs in foreground
make DEBUG_AGENTS=true up      # + mock agents
make PROFILE=prod up           # nginx frontend on :8080
make PROFILE= up               # no frontend container…
make react-dev                 # …run Vite on the host
make PROMETHEUS_SYSTEM_TESTING=true up  # :8001
make ps ; make logs SERVICE=client-agent
```

|||

::: callout bad
**`make up` and `make restart` wipe all agent registrations.** Every run does a full `down` and deletes the LiteLLM DB. In-tree agents re-register because they restart too. An **external agent** (your template agent) must be restarted afterwards.
:::

{.small}
`restart` = the same without `--build`. `ng-up` / `ng-restart` skip regenerating the agents file. `docker-compose.override.yml` is picked up automatically if present (gitignored).
::::

---

## From one Makefile line to every `FROM` {eyebrow="How the platform selects the base image"}

::: grid 3 gap=22px
#### ① platform/Makefile (the pin) {.acc}

```bash {.sm hl=4-5}
ifeq ($(LOCAL_SDK),true)
…_REPO := prometheus_api
…_HASH := local   # make base-image
else
…_REPO ?= containers.github.inl.gov/…
…_HASH ?= <tag>
endif
```

{.tiny}
`-include .env` comes first, so `.env` or the command line wins. `…` = `PROMETHEUS_API_BASE_IMAGE`.

|||

#### ② compose (build arg) {.acc}

```yaml {.sm}
# docker-compose.yml
x-build-args:
  PROMETHEUS_API_BASE_IMAGE_REPO: …
  PROMETHEUS_API_BASE_IMAGE_HASH:
    ${PROMETHEUS_API_BASE_IMAGE_HASH:-}
# agents/<x>/docker-compose.yml
args:
  - PROMETHEUS_API_BASE_IMAGE_REPO=…
  - PROMETHEUS_API_BASE_IMAGE_HASH=
      ${PROMETHEUS_API_BASE_IMAGE_HASH}
```

|||

#### ③ every Dockerfile {.acc}

```docker {.sm}
ARG PROMETHEUS_API_BASE_IMAGE_REPO=\
  containers.github.inl.gov/genesis/prometheus_api
ARG PROMETHEUS_API_BASE_IMAGE_HASH
FROM ${PROMETHEUS_API_BASE_IMAGE_REPO}:\
  ${PROMETHEUS_API_BASE_IMAGE_HASH}
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --no-dev \
  --no-install-project --inexact
```

{.tiny}
(Each `ARG`/`FROM` is one line in the real file.)
:::

:::: grid 3
::: card
#### Try another SDK version

```bash {.xs}
make PROMETHEUS_API_BASE_IMAGE_HASH=latest up
```

{.small}
Then read `sdk/docs/agent/AGENT_MIGRATIONS.md`. The pin and `latest` can differ: `latest` moves with every SDK change merged to `dev`. The client-agent's loop needs LLM tool calling (≥ v0.13.0), so don't pin lower.
:::

::: card
#### Trap: an empty line in `.env`

{.small}
An uncommented `PROMETHEUS_API_BASE_IMAGE_HASH=` overrides the Makefile default with **empty** (make's `?=` does not apply to defined variables), which breaks the `FROM`.
:::

::: card
#### Trap: plain `docker compose`

{.small}
Compose's default is empty. Always build through `make`, or export the variable yourself.
:::
::::

---

## Inside `sdk/Dockerfile` {eyebrow="What the base image provides"}

::: grid 2 gap=28px
```docker {.xs}
FROM ghcr.io/astral-sh/uv:0.11.25-python3.12-trixie-slim\
@sha256:1b9ee303…                  # digest-pinned

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.pem \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-bundle.pem \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-bundle.pem \
    UV_SYSTEM_PYTHON=1

# system CAs + every certs/*.pem (INL bundle)
RUN --mount=type=bind,source=certs,target=/tmp/certs \
    cp /etc/ssl/certs/ca-certificates.crt \
       /etc/ssl/certs/ca-bundle.pem; \
    cat /tmp/certs/*.pem >> /etc/ssl/certs/ca-bundle.pem

RUN apt-get install -y --no-install-recommends git

# locked runtime deps → system Python
RUN uv export --frozen --no-dev --no-emit-project \
      > requirements.txt && uv pip install -r requirements.txt
# the package itself
RUN uv pip install --no-deps /src
CMD ["python"]
```

|||

{.sm}
| You get | Details |
|---|---|
| Debian 13 slim, Python 3.12, `uv`, `git` | runs as root, no `WORKDIR` (agents set `/app`) |
| `prometheus_api` | PrometheusAgent, LLMClient, StorageClient, identity, credentials, artifacts |
| Server stack | `a2a-sdk[http-server]` 1.x, starlette, uvicorn |
| Clients | litellm, httpx, redis, fsspec (`deeplynx://`), PyJWT, pydantic, pyyaml |
| LLM profiles | `registry`, `inl_hpc`, `inl_litellm`, `amsc`, `anthropic`, `openai` |
| INL TLS trust | `certs/INL.pem` (157 CAs, incl. the INL root) |
| CLI | `prometheus-identity-keygen` |

{.small}
Your agent image adds only your own dependencies. That is why builds are small, and why `prometheus_api` must not appear in your `pyproject.toml`.
:::

---

## Every Makefile target {eyebrow="Reference"}

::: grid 2 gap=26px
{.xs}
| Target | Does |
|---|---|
| `help` | (default) list targets |
| `up` / `up-fg` | generate + key + wipe LiteLLM DB + `up --build` |
| `restart` / `restart-fg` | same without `--build` (still a full down) |
| `ng-up`, `ng-restart` (+`-fg`) | without regenerating the agents file |
| `down` | stop everything |
| `down-v` | stop and **delete volumes** (Valkey incl. sessions, both DBs, mesh cache, model caches) |
| `build` | generate + build images |
| `ps`, `logs` \[`SERVICE=`\] | status, follow logs |
| `generate`, `regenerate`, `clean-generated` | manage `docker-compose.agents.yml` |

|||

{.xs}
| Target | Does |
|---|---|
| `clear-litellm-db` | down + delete the LiteLLM volume |
| `clear-admin-users` | truncate users → the setup wizard runs again |
| `ensure-admin-encryption-key` | Fernet key into `.env` |
| `check-prerequisites` | .env + docker checks |
| `test-static` | infra tests, no Docker |
| `test-integration`, `test-infra` | against running containers |
| `test-system` | full system (needs `PROMETHEUS_SYSTEM_TESTING=true`) |
| `react-dev`, `react-build`, `react-check` | frontend on the host |
| `build-plain` | **broken** on dev (undefined variable) |
:::

{.small}
Variables: `PROFILE` (dev | prod | empty), `DEBUG_AGENTS`, `PROMETHEUS_SYSTEM_TESTING`, `PROMETHEUS_API_BASE_IMAGE_HASH`, `SERVICE`, `SKIP_PREREQUISITES=1`. The compose project name is `prometheus_platform`.

---

## Setup wizard, then a signing key {eyebrow="First login"}

:::: grid 2 gap=30px
::: steps
#### Open `http://localhost:5150`

{.small}
On a fresh admin-db the **setup wizard** appears. Create the first user with any local username and password (not your INL login); it becomes `admin`. (The old `prometheus/prometheus` login in the README no longer exists.)

#### Admin › Signing Keys

{.small}
Generate a key and **activate** it. From then on the backend mints an RS256 `userToken` for every chat turn and publishes the public key at `/.well-known/jwks.json`.

#### Chat

{.small}
Try `/help`, `/agents`, `/workflows`, then ask a real question.
:::

|||

::: callout bad
**Skip step 2 and every turn fails** with "No 'userToken' found in message metadata and USER_IDENTITY_REQUIRED=true". Agents require a user identity by default.
:::

::: card
#### Alternative to the admin UI

{.xs}
- Local only: `USER_IDENTITY_REQUIRED=false` in `.env`, then `make restart`. Requests run as user `local`.
- Setting `USER_IDENTITY_PRIVATE_KEY` is **not** enough on the stock stack: agents verify through the backend's JWKS (`JWKS_URL`), which lists only keys stored in admin-db. Use the admin UI.
:::

{.small}
Redo the wizard with `make clear-admin-users`. Sessions live in Valkey: a backend restart (even `make restart`) keeps you logged in, and a reload reopens the conversation you had open.
::::

---

## Check bottom-up: store → registry → backend → agents {eyebrow="Health checks"}

```bash {.sm}
source .env   # for the variables below

make ps                                                     # everything "Up"; litellm, dbs, backend "(healthy)"
docker exec agent-valkey valkey-cli -a "$REDIS_PASSWORD" ping  # → PONG
docker exec litellm-db pg_isready -U litellm                 # → accepting connections
docker exec admin-db   pg_isready -U admin

curl -s http://localhost:9977/health/liveliness               # → "I'm alive!"
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     http://localhost:9977/v1/models                           # → {"data":[{"id":"medium",…}]}
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     http://localhost:9977/v1/agents | python3 -m json.tool    # → registered agents

curl -s http://localhost:8600/healthz                          # → {"status":"ok"}
curl -s http://localhost:8600/.well-known/jwks.json            # → your active signing key

docker exec client-agent python -c "import urllib.request as u; \
  print(u.urlopen('http://synthesis-agent:8000/health').read())"   # → {"ok": true, "status": "healthy", …}
```

:::: grid 3
::: card
#### 401 from LiteLLM?

{.small}
Every LiteLLM route except health needs `Authorization: Bearer $LITELLM_MASTER_KEY`.
:::

::: card
#### `/healthz` through :5150?

{.small}
It is not under `/api`, so the frontend proxy does not forward it. Use :8600 directly.
:::

::: card
#### No agent healthchecks

{.small}
The agents and the client-agent have no Docker healthcheck (the backend does). "Up" only means started; check their logs.
:::
::::

---

## Ask the platform something {eyebrow="The real test"}

:::: grid 2 gap=30px
::: col
{.sm}
| Type in the chat | Expect |
|---|---|
| `/help` | the slash commands |
| `/agents` | form-filler, OSTI research, synthesis (plus debug agents) |
| `/workflows` | registered workflow templates |
| `/artifacts` | this conversation's artifacts |
| `/tasks [id]` | background tasks |
| "Find recent OSTI papers on SiC cladding" | routes to `search_literature`; watch the status stream |
:::

|||

#### Watch it happen {.acc}

```bash {.sm}
make logs SERVICE=client-agent
make logs SERVICE=osti-research-agent
make logs SERVICE=litellm
```

{.small}
In the client-agent log you see discovery (`GET /v1/agents`), each tool call the loop makes (status "Next step: …"), and the `/a2a/{agent}` call.

::: callout
A newly registered agent reaches the orchestrator's tool list within about 60 s (the capability-cache TTL), immediately on a skill miss, or right after `docker restart client-agent`.
:::
::::

---

## `DEBUG_AGENTS=true`: the reference agents {eyebrow="More to play with"}

:::: grid 2 gap=30px
```bash {.sm}
make DEBUG_AGENTS=true up
# or set DEBUG_AGENTS=true in .env
```

{.sm}
| Agent | Study it for |
|---|---|
| artifact-debug-agent (:8008) | DeepLynx artifacts, SVG→PNG, and an agent-owned workflow |
| corrosion-agent | `send_input_required` + context state |
| thermal-agent | a custom `json_type` with its own viewer |
| material-data-agent | many small skills on one agent |
| radiation-agent | input-required prompts |
| thread-pattern-agent | `PrometheusWorker`, `declare_long_running` |

|||

#### Prompts that exercise them {.acc}

{.sm}
- "Thermal analysis of SS316 at 550 °C" → thermal viewer
- "Comprehensive material analysis of SS347" → the `comprehensive_material_analysis` DAG workflow, which asks for **approval** before it runs
- "Make an image with the word Success" → SVG to DeepLynx (needs DeepLynx)
- `/artifact_debug.patriotic_usa_png` → starts the agent-owned workflow directly

::: callout
These are the best working examples of every pattern in the template tutorial. Read them in `agents/debug-agents/`.
:::
::::

---

## Code picks a flavor; the profile picks the model {eyebrow="LLM configuration for the deployment"}

:::: col
{.body}
Agent code asks for a **flavor** (`llm.medium(…)`). The deployment chooses a **profile** that maps flavors to real models. Resolution order in `LLMConfig.from_env()`:

1. `LLM_CONFIG_FILE`: a YAML path inside the container
2. `LLM_CONFIG_PROFILE`: an installed profile name
3. otherwise `registry`

{.small}
The platform default is `registry`: `proxy_url: os.environ/REGISTRY_URL`, so every call goes to **LiteLLM** at `http://litellm:4000/v1/chat/completions` with `model=<flavor>`.

::: callout warn
With the default `registry` profile, flavors are looked up in the platform's LiteLLM proxy. Its `litellm_config.yaml` on `dev` currently defines only `medium` (→ `anthropic/claude-sonnet-4-6`). Add the other aliases there (right), or switch to a profile such as `inl_litellm`, which defines all six. A flavor with no model behind it raises `LLMAliasError`.
:::
::::

---

## Adding flavors to the platform proxy {eyebrow="LLM configuration for the deployment"}

::: col
```yaml {.sm hl=7-15}
# prometheus_platform/platform/litellm_config.yaml
model_list:
  - model_name: medium
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: small
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: default
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  # …likewise large, vision, embedding
general_settings:   # unchanged
  master_key: "os.environ/LITELLM_MASTER_KEY"
  …
```

{.small}
Then `make restart` and check `curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" localhost:9977/v1/models`. Model IDs are examples; use what your key can access.
:::

---

## Switching the whole stack to another profile {eyebrow="Other providers"}

{.sm}
| Profile | Route | Key | default · small · medium · large · vision · embedding |
|---|---|---|---|
| `registry` | LiteLLM proxy at `$REGISTRY_URL` | proxy master key | whatever `litellm_config.yaml` defines {.hl} |
| `inl_litellm` | `https://litellm.inl.gov/v1` | `INL_LITELLM_API_KEY` | claude-sonnet-5-awsgov · sonnet-4-5 · sonnet-5 · opus-4-8 · opus-4-8 · text-embedding-3-large-gov-va |
| `inl_hpc` | `https://api.hpc.inl.gov/llm/v1` (vLLM) | `INL_HPC_API_KEY` | gemma-4-26B-A4B-it ×3 · gemma-4-31B-reasoning · gemma-4-26B · llama-nemotron-embed |
| `anthropic` | direct | `ANTHROPIC_API_KEY` (+ `EMBEDDING_API_KEY`) | opus-5 · haiku-4-5 · sonnet-5 · fable-5 · opus-5 · voyage-4-large |
| `amsc` | American Science Cloud | `AMSC_I2_API_KEY` | sonnet · haiku · sonnet · opus · opus · ada-002 |
| `anl_asksage` | ANL AskSage | `ASKSAGE_API_KEY` (+ `EMBEDDING_API_KEY`) | gpt-5.6-terra · gpt-5.4-nano · gpt-5.6-terra · gpt-5.6-sol · gpt-5.6-luna · voyage-4-large |
| `openai` | direct | `OPENAI_API_KEY` | gpt-5.6-terra · 5.4-nano · 5.6-terra · 5.6-sol · 5.6-luna · text-embedding-3-large |

:::: grid 2
```bash {.sm}
# .env: all platform agents talk to INL LiteLLM directly
LLM_CONFIG_PROFILE=inl_litellm
INL_LITELLM_API_KEY=sk-…
make restart
```

|||

::: callout
Setting `ANTHROPIC_API_KEY` alone does **not** change routing; only the profile or file does. Installed profiles are scaffolds: the model IDs are replaceable. The next session covers custom YAML files and adding profiles.
:::
::::

---

# DeepLynx: the data layer {.section num="DL"}
What the platform stores there, and how to run your own instance next to the stack.

---

## Why the platform needs it {eyebrow="DeepLynx"}

:::: grid 2 gap=30px
{.body}
**DeepLynx** (Nexus) is INL's open-source data warehouse (`github.com/idaholab/DeepLynx`): organizations → projects → records (items), files, tags, relationships, and timeseries, behind a REST API.

{.sm}
| Who | Uses DeepLynx for |
|---|---|
| client-agent | **every user upload** → stored, then registered as an artifact |
| agents | `send_deeplynx_artifact()` → `deeplynx://…/items/N` |
| backend | resolves `deeplynx://` to bytes for the viewers |
| agents consuming files | `get_artifact_file_path()` via fsspec |

|||

```yaml {.sm}
deeplynx://organizations/{org_id}/projects/{proj_id}/items/{item_id}
```

```python {.sm}
# any prometheus_api environment
import fsspec
from prometheus_api.storage_client import ConnectionConfig

fs = fsspec.filesystem("deeplynx",
        config=ConnectionConfig.from_env())
fs.get("deeplynx://organizations/1/projects/1/items/42",
       "/tmp/out/")          # → /tmp/out/42
```

::: callout warn
No DeepLynx configured → uploads show "DeepLynx storage is not configured" and are **not** passed to agents. Compose defaults to `https://deeplynx.inl.gov/api/v1`, which needs a key. A local instance is the easiest route for the hackathon.
:::
::::

---

## The usual DeepLynx traps {eyebrow="DeepLynx"}

::: col
{.sm .wrap-code}
| Symptom | Fix |
|---|---|
| Connection refused to `host.docker.internal` (Linux) | Docker Engine on Linux has no `host.docker.internal` by default. Add `extra_hosts: ["host.docker.internal:host-gateway"]` via a `docker-compose.override.yml`. |
| `AuthenticationError` / 401 | Key and secret swapped, or the secret was not copied completely. Generate a new key. |
| `ValueError: invalid literal for int() with base 10: ''` | `DEEPLYNX_ORG_ID` / `_PROJECT_ID` are empty (compose passes empty strings). Set them. |
| "Failed to get data source ID…" | The project has no default data source. Set `DEEPLYNX_DATA_SOURCE_ID` (list them with `examples/list_datasources.py` in prometheus_api). |
| `deeplynx://` URI won't resolve in your agent | The agent needs the **same org and project** in its `ConnectionConfig` as the URI. |
| Nothing on :5000 (macOS) | AirPlay Receiver has the port. |

{.tiny}
`DEEPLYNX_TIMEOUT`, `_MAX_RETRIES`, and `_VERIFY_SSL` appear in `sdk/.env.example` but are ignored; pass them as `ConnectionConfig` arguments instead.
:::

---

## It starts, but something is off {eyebrow="Troubleshooting · 1"}

{widths="470px|"}
| Symptom | Cause → fix |
|---|---|
| Every turn fails: "No 'userToken' found… USER_IDENTITY_REQUIRED=true" | No active signing key. Go to Admin › Signing Keys → generate + activate (or `USER_IDENTITY_REQUIRED=false`). |
| "userToken has expired" | A long turn exceeded `USER_IDENTITY_TTL` (7200 s). Raise it. |
| `LLMAliasError`: alias 'small' not available | The active profile has no model for that flavor. Under `registry`, add the alias to `litellm_config.yaml` and `make restart`, or switch `LLM_CONFIG_PROFILE`. |
| HTTP 401 from an LLM call in an agent | With a direct profile (`inl_litellm`, `amsc`, `anl_asksage`): the profile's key is missing in the agent's `.env`. With the `registry` profile: attach the master key only when `cfg.proxy_url` is set (next session). |
| The agent is running but not in `/agents` | The registration was wiped by `make up`/`restart`. `docker restart <agent>` re-registers it; it is routable within about 60 s. |

---

## It starts, but something is off (continued) {eyebrow="Troubleshooting · 2"}

{widths="470px|"}
| Symptom | Cause → fix |
|---|---|
| The orchestrator never calls your skill | A weak skill description or `usage_notes` (tags are not shown to it), a duplicate skill id, or a card URL the client-agent cannot reach (`EXTERNAL_AGENT_URL`). |
| Upload ignored: "DeepLynx storage is not configured" | Set `DEEPLYNX_*` and `make restart`. |
| Chat title stays as the raw first question | Title generation uses `llm.small`, which is missing under `registry`. Harmless. |
| Mesh viewer error "libGL.so.1" | An old backend image. Rebuild with `make up`. |
| "Live updates stopped — the server is unreachable" | The backend or Valkey restarted mid-stream. Reload: the session and the open conversation come back. |

---

## Where to look {eyebrow="Debugging toolkit"}

:::: grid 3 gap=20px
::: card
#### Logs

```bash {.xs}
make logs                    # all
make logs SERVICE=backend
docker logs -f client-agent
docker logs <agent> 2>&1 \
  | grep -i "Registered '"
```

{.small}
Everything logs to stdout. The "Registered" line appears only if the agent logs at INFO (the template does); `/v1/agents` is authoritative.
:::

::: card
#### State

```bash {.xs}
docker exec -it agent-valkey \
  valkey-cli -a "$REDIS_PASSWORD"
> KEYS artifacts:conv:*
> KEYS conversation:*
> KEYS capability_cache:v4:*
> KEYS session:*
```

{.small}
Conversation state, artifact catalog, capability cache (60 s TTL), task graph, browser sessions.
:::

::: card
#### Inside a container

```python {.xs}
docker exec client-agent env \
  | grep -E '^(REGISTRY_URL|LLM_CONFIG_)'
docker exec client-agent python -c "
import os, urllib.request as u
r = u.Request(
 'http://localhost:8000'
 '/discovery/refresh',
 method='POST', headers={
 'Authorization': 'Bearer '
 + os.environ['AGENT_SECRET']})
print(u.urlopen(r).read())"
```

{.small}
Force a discovery refresh. The images have Python but no `curl`.
:::
::::

::: callout
Reset ladder, from least to most destructive: `docker restart <svc>` → `make restart` → `make up` → `make clear-admin-users` → `make down-v` (deletes all volumes, history, and users).
:::
