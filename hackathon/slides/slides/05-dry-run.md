---
title: End-to-End Dry Run
footer: Day 1 · End-to-end dry run
accent: dry
index:
  time: '3:30'
  heading: End-to-end dry run
  color: var(--green)
  blurb: 'A command refresher for the hands-on session: platform check, scaffold and edit, run and route, practice PR to <code>genesis/hackathon</code>.'
---

## End-to-end dry run {eyebrow="3:30 pm · hands-on · 60 min"}
> Do everything from today yourself. Mentors circulate to unblock environment problems; raise your hand early.

:::: grid 4
::: card acc
<div class="kpi"><span class="v">1</span><span class="l">~10 min</span></div>

### Check

{.small}
Your platform from the homework is up and current, and you are logged in with an active signing key.
:::

::: card acc
<div class="kpi"><span class="v">2</span><span class="l">~15 min</span></div>

### Scaffold

{.small}
Run `setup_agent.py` from `agent-template/` in your platform clone, with a **unique** name (`hello-<you>`).
:::

::: card acc
<div class="kpi"><span class="v">3</span><span class="l">~15 min</span></div>

### Edit & call

{.small}
Change the skill so it greets by name. `make up`, check it registered, and get the chat to route to it.
:::

::: card acc
<div class="kpi"><span class="v">4</span><span class="l">~15 min</span></div>

### Practice PR

{.small}
Fork `genesis/hackathon`, commit your agent under `practice/<you>/`, open a PR to `main`, get a review.
:::
::::

:::: grid 3 wrap-code
::: callout good
**Done** = `/agents` lists your agent, a chat message returns your greeting, and your PR has an approval.
:::

::: callout warn
Use **your own** card name and skill ID. The registry replaces agents with the same name, so two identical "Hello World Agent"s evict each other.
:::

::: callout info
Folder layout: `~/prometheus/prometheus_core/{platform, sdk, agent-template}` plus your `~/prometheus/hello-<you>`. `setup_agent.py` finds `../platform/.env` by itself.
:::
::::

---

## Platform: is it ready? {eyebrow="Refresh · 1"}

:::: grid 2 gap=26px
```bash {.xs}
cd ~/prometheus/prometheus_core
git pull --rebase upstream devel   # latest devel
cd platform
make up
make ps

# verify
set -a; source .env; set +a
curl -s localhost:8600/healthz
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     localhost:9977/v1/agents | python3 -m json.tool
```

|||

1. Open `http://localhost:5150`; create the admin in the setup wizard if you haven't
2. Admin › Signing Keys → **generate + activate**
3. Chat: `/agents`, then ask a question
4. Upload any small file: it should appear in DeepLynx

::: callout warn
Platform not up yet? Use the **bonus slide** at the end of this deck, and the bonus section of deck 03.
:::
::::

---

## Agent: scaffold and edit {eyebrow="Refresh · 2"}

```bash {.sm}
cd ~/prometheus/prometheus_core/agent-template   # same clone
python3 setup_agent.py "Hello <You>" ../../hello-<you>   # no ~
#  → card "Hello <You> Agent"
#  skill id: hello_<you>_greeting   (unique!)
#  copy secrets from ../platform/.env? yes
cd ~/prometheus/hello-<you>

# edit agent_card.json: skill description + usage_notes
#   "Greets a person by name. Use when the user asks
#    to be greeted or says hello to <You>."
#   inputSchema: rename input_data → person_name

# edit agent.py → _execute:
#   name = params.get("person_name")
#   return {"status": "success",
#           "greeting": f"Hello, {name}, from <you>!"}

uv sync
uv pip install -e ~/prometheus/prometheus_core/sdk
uv run pytest    # update the tests; keep one send_status_update
uv run ruff check .
make up          # joins the platform network
make logs
```

---

## Agent: run it and see it routed {eyebrow="Refresh · 3"}

::: col
```bash {.sm}
# registered?
docker logs hello-<you>-agent 2>&1 | grep "Registered '"
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  localhost:9977/v1/agents | grep -o '"agent_name": *"[^"]*"'

# make the orchestrator notice now (else ≤ 60 s)
docker restart client-agent
```

{.sm}
1. Chat: `/agents` shows your agent
2. Ask: "Please greet Marie Curie on behalf of &lt;You&gt;"
3. Watch `make logs` in your agent dir
4. Stretch: set `"streaming": true`, add a `send_status_update`, then `make up` again

{.xs .wrap-code}
| If… | then |
|---|---|
| "The Prometheus Platform must be launched first" | start the platform first (the network is missing) |
| not in `/agents` | the platform was restarted: `docker restart hello-<you>-agent` |
| never routed | sharpen the description; `docker restart client-agent` |
| LLM 401 (if you added LLM calls) | the key for your `LLM_CONFIG_PROFILE` in `.env` |
| `ModuleNotFoundError` in the container | add a `COPY` line to the Dockerfile |
| `No module named 'prometheus_api'` in `uv run pytest` | `uv pip install -e ~/prometheus/prometheus_core/sdk` |
| test fails: no status update sent | keep a `send_status_update` in `_execute`, or drop that assertion |
:::

---

## Practice PR to `genesis/hackathon`, with a rebase {eyebrow="Refresh · 4"}

:::: grid 2 gap=24px
```bash {.xs hl=18}
cd ~/prometheus
gh repo fork genesis/hackathon --clone=false
git clone git@github.inl.gov:<you>/hackathon.git
cd hackathon
git remote add upstream git@github.inl.gov:genesis/hackathon.git
git fetch upstream
git switch -c feature/hello-<you> upstream/main

mkdir -p practice/<you>
cp -r ../hello-<you>/{agent.py,agent_card.json,README.md,tests} \
   practice/<you>/
git status                     # NO .env in the list!
git add practice/<you>
git commit -m "Add hello-world agent for <you>"

# someone else merged first? replay on top
git pull --rebase upstream main

git push -u origin HEAD        # later: git push --force-with-lease
gh pr create --repo genesis/hackathon \
  --base main --head <you>:feature/hello-<you> \
  --title "Practice: hello from <you>" \
  --body "Dry-run PR. Tested: uv run pytest, routed in UI."
```

|||

{.sm}
1. Ask your neighbour to review: `gh pr view <n> --web`
2. Reviewer: leave one inline comment
3. Author: push a fix commit and reply "Fixed in &lt;sha&gt;"
4. Reviewer: resolve the thread and **approve**
5. A mentor merges

::: callout warn
Repo **`genesis/hackathon`**, base `main`. `--force-with-lease` only on your own feature branch.
:::

{.xs .wrap-code}
| If… | then |
|---|---|
| cannot fork or see `genesis/hackathon` | org access (team `open`); ask a mentor |
| rebase conflict | edit → `git add` → `git rebase --continue` (or `--abort`) |
| push rejected (non-fast-forward) | after a rebase: `git push --force-with-lease` |
| no `gh` | `brew install gh`, or the release binary in `~/.local/bin`; or use the Fork / Compare & pull request buttons |
::::

Note: Practice PRs go to genesis/hackathon main under practice/&lt;user&gt;/; team agents on Day 2 go under agents/&lt;team_name&gt;/.

---

# Bonus: catch-up slides {.section .bonus num="+"}
For participants whose platform from the homework does not run yet.

---

## Platform from scratch: clone, configure, start, verify {eyebrow="Bonus · Refresh · 1"}

::: grid 2 gap=24px
```bash {.xs}
# once
gh repo fork idaholab/prometheus_core --clone=false
git clone git@github.com:<you>/prometheus_core.git
cd prometheus_core
git remote add upstream \
  git@github.com:idaholab/prometheus_core.git
git fetch upstream
cd platform            # the stack lives here

cp .env.example .env
echo "LOCAL_SDK=true" >> .env   # base image from ../sdk
# fill: ANTHROPIC_API_KEY, AGENT_SECRET, REDIS_PASSWORD,
#       BACKEND_JWT_SECRET, LITELLM_MASTER_KEY,
#       LITELLM_DB_PASSWORD, ADMIN_DB_PASSWORD
python3 -c "import secrets; print(secrets.token_hex(32))"

make up                   # long first build; make logs to watch
make ps
```

|||

```bash {.xs}
# 3. verify (bottom-up)
set -a; source .env; set +a
curl -s localhost:9977/health/liveliness
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     localhost:9977/v1/agents | python3 -m json.tool
curl -s localhost:8600/healthz
```

{.sm}
1. Open `http://localhost:5150` → setup wizard → create the admin
2. Admin › Signing Keys → **generate + activate**
3. Chat: `/agents`, then ask a question

{.xs .wrap-code}
| If… | then |
|---|---|
| `FROM …prometheus_api:` error or pull `unauthorized` | `LOCAL_SDK=true` missing in `.env` |
| "No 'userToken' found" | activate a signing key |
| port already in use | `make down`, or change `*_PORT` in `.env` |
:::

---

# Appendix: reference {.section .appendix num="A"}
The original refresher slide, kept for reference.

---

## Platform: is it ready? {eyebrow="Refresh · 1"}

:::: grid 2 gap=26px
```bash {.sm}
cd ~/prometheus/prometheus_core
# 1. your fork as origin (deck 02), then update
git remote rename origin upstream
gh repo fork idaholab/prometheus_core --clone=false
git remote add origin \
  git@github.com:<you>/prometheus_core.git
git pull --rebase upstream devel

# 2. the stack from the homework
cd platform
make up
make ps

# 3. verify (bottom-up)
set -a; source .env; set +a
curl -s localhost:9977/health/liveliness
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     localhost:9977/v1/agents | python3 -m json.tool
curl -s localhost:8600/healthz
```

|||

1. Open `http://localhost:5150`; create the admin in the setup wizard if you haven't
2. Admin › Signing Keys → **generate + activate**
3. Chat: `/agents`, then ask a question
4. Upload any small file: it should appear in DeepLynx

::: callout warn
Platform not up yet? Use the **bonus slide** at the end of this deck, and the bonus section of deck 03.
:::
::::
