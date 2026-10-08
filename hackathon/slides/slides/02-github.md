---
title: GitHub & PR Workflow
footer: Day 1 · GitHub & PR workflow
accent: gh
index:
  time: '1:00'
  heading: GitHub &amp; PR workflow
  color: var(--violet)
  blurb: Where your code goes (<code>genesis/hackathon</code>), the branching model, forking, the daily loop with <code>git pull --rebase</code>, conflicts and force-pushes, commits, PRs with JIRA, review, the practice PR.
---

# GitHub overview &<br>PR workflow {.title kicker="Day 1 · 1:00 pm" pills="All participants | 45 min | github.inl.gov/genesis"}
Where your code goes, how to branch and rebase, and how to get a PR reviewed and merged.

---

## By the end you can… {eyebrow="This session"}

:::: grid 3
::: card acc
<div class="kpi"><span class="v">1</span></div>

### Find your repo

{.small}
Know where your code goes (`genesis/hackathon`) and why you fork it.
:::

::: card acc
<div class="kpi"><span class="v">2</span></div>

### Work on a branch

{.small}
Branch, commit, stay current with `git pull --rebase`, and push safely.
:::

::: card acc
<div class="kpi"><span class="v">3</span></div>

### Get merged

{.small}
Open a PR reviewers can act on, and review someone else's.
:::
::::

::: callout info
You'll do all three for real at 3:30 pm, with a practice PR. On Day 2 every team works the same way.
:::

---

## `genesis/hackathon`: one repo, one folder per team {eyebrow="Where your code goes"}

::: grid 2 gap=30px
```text {.sm}
hackathon/                # github.inl.gov/genesis/hackathon
├── practice/
│   └── <you>/            # today: your hello-world agent
├── agents/
│   ├── <team_name>/      # Day 2: your team's agent
│   │   ├── agent.py
│   │   ├── agent_card.json
│   │   └── tests/
│   └── …
└── hollowmere_almanac.md
```

|||

- Team `open` has **write** access. Work in your own **fork** (or a branch) and open PRs to `genesis/hackathon`.
- `main` is protected: changes reach it only through a PR with one approval, and force-pushes are blocked.
- The platform repos (`prometheus_platform`, `prometheus_api`, the template) are read-only for this hackathon. Contributing to the platform later? **Always fork it**: a ruleset allows no branches there except `dev`.
:::

---

# Branching strategy {.section num="02"}
Git Flow: a production branch, an integration branch, short-lived feature branches, and release/hotfix lanes.

---

##  {eyebrow="Our model · develop = dev in prometheus_platform" content="center" content-style="flex:1; min-height:0" nofit style="gap:10px"}

<img alt="Git Flow branching strategy diagram" class="fit" src="assets/git_branches.png" style="max-height:740px"/>

---

## You work on feature branches {eyebrow="What it means for you"}

::: grid 2 gap=30px
| Branch | Who touches it |
|---|---|
| `feature/<desc>` | **you**: one per piece of work, in your fork {.hl} |
| `main` (hackathon, api, template)<br>`dev` (platform) | the integration branch: PRs only |
| `release/*`, `hotfix/*`, platform `main` | maintainers, for releases |

|||

- Name branches `feature/<team>-<what>`: `feature/neutron-plot-skill`.
- Branch from the latest integration branch, keep it short-lived, delete it after the merge.
- Never commit to `main` or `dev` directly.
:::

---

## Fork and clone: `origin` is yours, `upstream` is genesis {eyebrow="Once"}

:::: cols 1.35fr 1fr gap=28px
```bash {.sm}
export GH_HOST=github.inl.gov
gh repo fork genesis/hackathon --clone=false

cd ~/prometheus
git clone git@github.inl.gov:<you>/hackathon.git
cd hackathon
git remote add upstream \
  git@github.inl.gov:genesis/hackathon.git

git config pull.rebase true
git config rebase.autoStash true
```

|||

{.sm}
- `origin` = your fork: you push here.
- `upstream` = genesis: PRs go here, and you pull updates from here.
- Check with `git remote -v`.

::: callout
Each teammate forks separately. Everyone's PRs meet in `genesis/hackathon`.
:::

::: callout info
No `gh`? Install it (deck 02 bonus) or use the **Fork** and **Compare & pull request** buttons on the web.
:::
::::

---

## The daily loop {eyebrow="Every piece of work"}

::: cols 1.35fr 1fr gap=28px
```bash {.sm hl=8}
git fetch upstream
git switch -c feature/neutron-plot-skill upstream/main

# edit, test, commit small steps
git add -p
git commit -m "Add the plot skill with a column form"

git pull --rebase upstream main   # stay current
git push -u origin HEAD

gh pr create --repo genesis/hackathon --base main \
  --head <you>:feature/neutron-plot-skill
```

|||

{.sm}
1. **Branch** from the latest `upstream/main`
2. **Commit** small, logical steps
3. **Rebase** onto upstream before pushing
4. **Push** to your fork
5. **Open a PR** to genesis

{.small}
For the platform repo the integration branch is `dev`: `git pull --rebase upstream dev`, `--base dev`.
:::

---

## `git pull --rebase upstream main`, visually {eyebrow="What rebase does"}
> In the hackathon repo. For the platform the same picture applies to `upstream/dev`.

<svg aria-label="Rebase diagram" height="380" role="img" viewbox="0 0 1400 380" width="1400">
<style>
        .ln{stroke:#9aa8ba;stroke-width:4;fill:none}
        .dv{fill:#d8c93a;stroke:#fff;stroke-width:3}
        .ft{fill:#6b4fbb;stroke:#fff;stroke-width:3}
        .ftn{fill:#fff;stroke:#6b4fbb;stroke-width:3;stroke-dasharray:4 3}
        .lb{font:600 17px 'JetBrains Mono',monospace;fill:#35455b}
        .tt{font:700 22px Archivo,sans-serif;fill:#0e1b2c}
        .cm{font:15px 'JetBrains Mono',monospace;fill:#66768c}
      </style>
<text class="tt" x="20" y="34">Before</text>
<path class="ln" d="M60 110 H600"></path>
<path class="ln" d="M200 110 C240 110 240 180 280 180 H440" style="stroke:#6b4fbb"></path>
<circle class="dv" cx="100" cy="110" r="15"></circle><circle class="dv" cx="200" cy="110" r="15"></circle>
<circle class="dv" cx="400" cy="110" r="15"></circle><circle class="dv" cx="520" cy="110" r="15"></circle>
<circle class="ft" cx="320" cy="180" r="15"></circle><circle class="ft" cx="430" cy="180" r="15"></circle>
<text class="lb" x="560" y="94">upstream/main</text>
<text class="lb" x="460" y="186">feature/x</text>
<text class="cm" x="300" y="224">A</text><text class="cm" x="422" y="224">B</text>
<text class="cm" x="385" y="80">C</text><text class="cm" x="507" y="80">D</text>
<text class="tt" x="720" y="34">After</text>
<path class="ln" d="M760 110 H1260"></path>
<path class="ln" d="M1220 110 C1250 110 1250 180 1280 180 H1340" style="stroke:#6b4fbb"></path>
<circle class="dv" cx="800" cy="110" r="15"></circle><circle class="dv" cx="900" cy="110" r="15"></circle>
<circle class="dv" cx="1060" cy="110" r="15"></circle><circle class="dv" cx="1220" cy="110" r="15"></circle>
<circle class="ft" cx="1290" cy="180" r="15"></circle><circle class="ft" cx="1345" cy="180" r="15"></circle>
<text class="lb" x="1040" y="80">upstream/main</text>
<text class="cm" x="1045" y="150">C</text><text class="cm" x="1207" y="150">D</text>
<text class="cm" x="1266" y="224">A′</text><text class="cm" x="1330" y="224">B′</text>
<text class="lb" x="1150" y="258">feature/x</text>
<text class="cm" x="20" y="300">Your commits A and B are replayed on top of the new tip D as new commits A′ and B′ (new SHAs).</text>
<text class="cm" x="20" y="328">That is why the next push needs --force-with-lease, and why rebasing an open PR restarts review.</text>
</svg>

:::: grid 2
::: card
#### Tidy before review

```bash {.xs}
git rebase -i upstream/main
# squash fixups, reword
git commit --fixup <sha>
git rebase -i --autosquash …
```

{.tiny}
Interactive rebase needs a terminal editor.
:::

::: card
#### Repeated conflicts

```bash {.xs}
git config rerere.enabled true
```

{.small}
git remembers how you resolved a conflict and reapplies it on the next rebase.
:::
::::

---

## Conflicts and force-pushes {eyebrow="After a rebase"}

:::: grid 3
::: card
#### A conflict during rebase

```bash {.xs}
git status          # which files
# fix them, then
git add <file>
git rebase --continue
git rebase --abort  # start over
```
:::

::: card
#### Pushing a rebased branch

```bash {.xs}
git push --force-with-lease
```

{.small}
A rebase rewrites your commits, so the push must be forced. `--force-with-lease` refuses if someone else pushed in the meantime. Never plain `--force`.
:::

::: card
#### Rebasing an open PR

{.small}
Any new push clears existing approvals. Rebase **before** asking for review; during review, push new commits instead.
:::
::::

::: callout warn
Force-push only **your own** feature branch, never a branch a teammate also works on.
:::

---

## Commit messages people can read later {eyebrow="Commits"}

::: grid 2 gap=30px
- **Imperative subject, under 72 characters**: "Add…", "Fix…", "Handle…".
- **The body explains why**; the diff shows what.
- One topic per commit.
- **Never commit `.env`**, keys, or tokens. Check `git status` before every commit.

|||

#### Good {.acc}

```text {.sm}
Handle thousands separators in table cells
Ask for the x column when none was given
Return the matched caption with the table id
```

#### Not helpful {.acc}

```text {.sm}
wip
fix
changes
```
:::

---

## A description reviewers can act on {eyebrow="Opening a PR"}

::: cols 1.2fr 1fr gap=28px
```markdown {.sm}
JIRA: PPLT-123            # project convention

## What
Plot skill asks for columns when none are given.

## Why
"plot this" on a CSV used to fail.

## How it was tested
- uv run pytest, uv run ruff check .
- Chat: uploaded the CSV, said "plot this",
  picked columns in the form, plot rendered.
```

|||

{.sm}
- **Title** like a commit subject.
- **Small and focused**: one topic per PR.
- Say **how you tested** it.
- In project work, reference the **JIRA task** (`PPLT-…`).
- Still in progress? `gh pr create --draft`.
:::

---

## Reviewing, and being reviewed {eyebrow="Code review"}

:::: grid 2 gap=30px
::: card
### As an author

{.sm}
- Reply to every comment: "Fixed in `a1b2c3d`", or why not.
- Push fixes as new commits during review.
- Never approve your own PR (you can't).
:::

::: card
### As a reviewer

{.sm}
- Be concrete: which line, which input breaks it.
- Separate "must fix" from "nit".
- Check the tests test what they claim.
:::
::::

::: callout good
The Day 2 gate needs one PR **approved by someone outside your team**. Pair up with another team early.
:::

---

## Your practice PR to `genesis/hackathon` {eyebrow="Practice at 3:30"}

:::: grid 2 gap=30px
```bash {.xs}
cd ~/prometheus
export GH_HOST=github.inl.gov
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

git push -u origin HEAD
gh pr create --repo genesis/hackathon --base main \
  --head <you>:feature/hello-<you> \
  --title "Practice: hello from <you>" --body "Dry run PR."
```

|||

{.sm}
1. Open the PR to **`genesis/hackathon`**, base `main`. Practice agents go in `practice/<you>/`; on Day 2 your team's agent goes in `agents/<team_name>/`.
2. Ask a neighbour to review. Leave one comment, answer it, and resolve it.
3. The reviewer approves; a mentor merges.
4. Rebase exercise: after someone else's PR merges, run `git pull --rebase upstream main` on your next branch.

::: callout warn
Double-check `git status` before committing: your agent directory contains a `.env` with the platform secrets. Copy only the files listed; never commit a `.env`.
:::
::::

Note: Assumes genesis/hackathon main has a ruleset (1 approval, no force-push) before the event; team open has write access. The repo .gitignore already excludes .env.

---

## Git & gh commands on one page {eyebrow="Cheat sheet"}

::: grid 3 gap=18px
```bash {.xs}
# setup (once)
export GH_HOST=github.inl.gov
gh auth login --hostname github.inl.gov
gh repo fork genesis/<repo> --clone=false
git clone git@github.inl.gov:<you>/<repo>.git
git remote add upstream \
  git@github.inl.gov:genesis/<repo>.git
git config pull.rebase true
git config rebase.autoStash true
git config rerere.enabled true
```

|||

```bash {.xs}
# every feature
git fetch upstream
git switch -c feature/<desc> upstream/main
#   (upstream/dev for the platform)
git commit -m "Imperative subject"
git pull --rebase upstream main
git push -u origin HEAD
git push --force-with-lease
gh pr create --repo genesis/<repo> \
  --base main --head <you>:feature/<desc>
```

|||

```bash {.xs}
# during review
gh pr status
gh pr view --comments
gh pr checks
gh pr diff
git rebase --continue | --abort
git log --oneline --graph \
  upstream/main..HEAD

# after merge
git switch -d upstream/main
git branch -D feature/<desc>
git push origin --delete feature/<desc>
```
:::

::: callout
Next: **Your local platform** (1:45 pm). Keep your platform running; we look at what it runs for you.
:::

---

# Bonus: catch-up slides {.section .bonus num="+"}
For participants who could not finish the homework: GitHub access, tokens, and fresh clones.

---

## Getting in: org, git, and registry {eyebrow="Bonus · Access"}

:::: grid 3
::: card tag="1 · org membership"
#### Access through the `open` team

{.small}
The org default permission is **none**. Team `open` (88 members) gives access to 20 shared repos: the core three, agent-sandbox-mcp, gmsh, bim, requirements, component agents, and `hackathon` (with **write**). Some agent repos need extra access; repo admins grant it.

{.small}
You **fork** and open PRs from your fork. For the platform this is required (only `dev` may exist as a branch there).
:::

::: card tag="2 · git transport"
#### SSH key or gh credential helper

{.small}
Add a key at `github.inl.gov/settings/keys`, then:

```text {.xs}
ssh -T git@github.inl.gov
```

{.small}
Or use HTTPS and let `gh` handle credentials:

```bash {.xs}
gh auth login --hostname github.inl.gov
export GH_HOST=github.inl.gov
```
:::

::: card tag="3 · container registry"
#### PAT with `read:packages`

{.small}
Needed to pull the `prometheus_api` base image. Create a classic token at `github.inl.gov/settings/tokens/new`:

```bash {.xs}
echo $GITHUB_PAT | docker login \
  containers.github.inl.gov \
  --username <you> --password-stdin
```
:::
::::

::: callout info
**`gh`, the GitHub CLI**, is used in these slides. Install it with `brew install gh` (needs admin rights), or copy the release binary from `github.com/cli/cli/releases` into `~/.local/bin` (no admin). Then `gh auth login --hostname github.inl.gov`. Without `gh`: the **Fork** button and **Compare & pull request** on the web do the same.
:::

::: callout warn
No access yet? Tell a mentor now. Repo admins can add you; waiting until 3:30 pm will cost you the dry run.
:::

---

## Fresh start: fork, then clone `origin` is yours, `upstream` is genesis {eyebrow="Bonus · Fork & clone conventions"}

:::: grid 2 gap=30px
```bash {.sm}
# 1. fork in the web UI, or:
export GH_HOST=github.inl.gov
gh repo fork genesis/prometheus_platform --clone=false

# 2. clone YOUR fork
git clone git@github.inl.gov:<you>/prometheus_platform.git
cd prometheus_platform

# 3. add the org repo as "upstream"
git remote add upstream \
  git@github.inl.gov:genesis/prometheus_platform.git
git fetch upstream
git remote -v
#   origin    …:<you>/prometheus_platform  (push here)
#   upstream  …:genesis/prometheus_platform (PR target)

# 4. make rebase the default for pull
git config pull.rebase true
git config rebase.autoStash true
```

|||

::: card
#### Why fork?

{.small}
**Always fork the platform**: a ruleset blocks creating any branch on `genesis/prometheus_platform` except `dev`, so the PR has to go from `<you>:feature/x` to `genesis:dev`. Forking works the same way for every other genesis repo.
:::

::: card
#### Clone side by side

{.small}
`setup_agent.py` looks for `../prometheus_platform/.env` to copy secrets into your new agent. Keep this layout:

```text {.xs}
~/prometheus/
├── prometheus_platform/
├── prometheus_agent_template/
└── my-agent/            # generated
```
:::
::::

---

## Clone the agent template {eyebrow="Bonus · Homework"}

```bash
cd ~/prometheus
git clone git@github.inl.gov:genesis/prometheus_agent_template.git
# no SSH key? use HTTPS and let gh handle credentials:
gh auth login --hostname github.inl.gov
git clone https://github.inl.gov/genesis/prometheus_agent_template.git
```

::: callout
Keep it next to `prometheus_platform`: `setup_agent.py` looks for `../prometheus_platform/.env` to copy the platform secrets into your new agent.
:::

---

# Appendix: reference {.section .appendix num="A"}
Reference material behind the talk. Skipped in the session; use it when you need the details.

---

## What you will be able to do afterwards {eyebrow="This session"}

:::: grid 3
::: card acc
### Find your way

{.sm}
- Know the three core repos and what lives where
- Understand how `prometheus_api` reaches every agent (the base image)
- Know which branch each repo integrates on
:::

::: card acc
### Work safely

{.sm}
- Fork, clone, add `upstream`
- Branch `feature/<desc>` from the integration branch
- Stay current with `git pull --rebase upstream dev`
- Push with `--force-with-lease` to *your fork*
:::

::: card acc
### Get merged

{.sm}
- Run the local checks (they *are* the CI for most repos)
- Open a PR with `gh pr create` against the right base
- Pass review: 1 approval, all threads resolved
:::
::::

::: callout info
Hands-on is at 3:30 pm: you will open a practice PR to `genesis/hackathon`, the repo where every team's agent lands on Day 2. Nothing today touches the platform's `dev` or `main`.
:::

---

## `github.inl.gov/genesis` {eyebrow="The organization"}
> INL's GitHub Enterprise Server. The org profile (`genesis/.github` → `profile/README.md`) lists what matters most.

:::: grid 2 gap=30px
### ⚙️ Platform: the three core repos {.acc}

::: card
#### 🧰 prometheus_api

{.small}
"Agent base class and storage helpers." It also contains LLMClient, identity, and the artifact catalog.
:::

::: card
#### 🚀 prometheus_platform

{.small}
"Orchestration, agent registry, frontend, core agents."
:::

::: card
#### 🤖 prometheus_agent_template

{.small}
"Get started on writing your own Prometheus agent here!"
:::

|||

### 🔗 Links on the profile {.acc}

| Link | Used for |
|---|---|
| 📚 Prometheus Wiki (Confluence) | Software design and planning documents |
| 📖 Confluence | Project management |
| 🗂️ JIRA project `PPLT` | Issues and work items |
| 📦 Proposal Box | Proposal documents |

::: callout
27 repos in the org. All are private except `.github` (the org profile). Container images are published at `containers.github.inl.gov/genesis/<repo>`. Work is tracked in JIRA project `PPLT`: **reference the JIRA task in every PR** (e.g. `PPLT-123`).
:::
::::

---

## What is in the org {eyebrow="Repository map"}

::: grid 3 gap=16px
#### Core platform {.acc}

<table class="t xs">
<tr><td><b>prometheus_platform</b></td><td>default <code>dev</code></td></tr>
<tr><td><b>prometheus_api</b></td><td><code>main</code> · v0.13.0</td></tr>
<tr><td><b>prometheus_agent_template</b></td><td><code>main</code></td></tr>
<tr><td>.github</td><td>org profile + wiki bot</td></tr>
</table>

<h4 class="acc" style="margin-top:6px">Tooling</h4>

<table class="t xs">
<tr><td><b>agent-sandbox-mcp</b></td><td>notebook MCP sandbox</td></tr>
<tr><td>mcps</td><td>FastMCP server template</td></tr>
<tr><td>a2a-tester</td><td>debug UI (still A2A v0.3)</td></tr>
<tr><td>reactor-dt-modules</td><td>digital-twin library</td></tr>
<tr><td>pythia</td><td>surrogate model repo</td></tr>
</table>

|||

#### Agents (A2A / PrometheusAgent) {.acc}

<table class="t xs">
<tr><td><b>gmsh_agent</b></td><td>STEP → tet mesh</td></tr>
<tr><td><b>bim_agent</b></td><td>"Alchemy" IFC4 BIM</td></tr>
<tr><td><b>requirements_agent</b></td><td>plant sizing + reqs</td></tr>
<tr><td>muninn</td><td>RAVEN UQ</td></tr>
<tr><td>open_pronghorn-agent</td><td>RANS CFD</td></tr>
<tr><td>pythia-agent</td><td>ATR valve surrogate</td></tr>
<tr><td>component_*_agent (×3)</td><td>inspection · QA · testing reports</td></tr>
<tr><td>data-catalog-search-agent</td><td>DeepLynx search</td></tr>
<tr><td>aegis</td><td>safety analysis</td></tr>
</table>

|||

#### More agent work {.acc}

<table class="t xs">
<tr><td>system-thermal-hydraulics</td><td>TH network solver</td></tr>
<tr><td>cubit-energy-agent</td><td>Cubit meshing (ADK)</td></tr>
<tr><td>amsc-client-agent</td><td>American Science Cloud</td></tr>
<tr><td>am-print-planner</td><td>preform/slicer agents</td></tr>
<tr><td>nuclear_safety_agent</td><td>Chainlit app (not A2A)</td></tr>
<tr><td>cad-agent</td><td>build123d CAD app</td></tr>
<tr><td>multiphysics-uq-agent</td><td>empty</td></tr>
</table>

<div class="callout" style="font-size:16px">Only <b>prometheus_platform</b> has a <code>dev</code> branch. Every other repo takes PRs directly into <code>main</code>. Some repos listed here are not readable through the <code>open</code> team; ask if you need one.</div>
:::

---

## One SDK, delivered as a base image {eyebrow="How the repositories relate"}

<div class="dg">
<div class="row" style="gap:0; align-items:stretch">
<div class="box navy" style="width:330px"><b>prometheus_api</b><span class="small">package <code>prometheus-api</code></span><span class="small">push to <code>main</code> → CI "Tests"</span></div>
<div class="arrow-h" style="width:120px"><span>docker build</span></div>
<div class="box violet" style="flex:1"><b>Base image</b><span class="mono">containers.github.inl.gov/genesis/prometheus_api:&lt;tag&gt;</span><span class="small">Python 3.12 + uv + git + prometheus_api + a2a-sdk/starlette/uvicorn/litellm/httpx/redis/fsspec + INL CA bundle</span></div>
</div>
<div class="grid g2" style="gap:24px"><div class="arrow-v"><span>FROM …:${PROMETHEUS_API_BASE_IMAGE_HASH}</span></div><div class="arrow-v"><span>FROM …:${…_HASH:-latest}</span></div></div>
<div class="row" style="gap:24px">
<div class="box sky" style="flex:1"><b>prometheus_platform</b><span class="small">backend, client-agent, and every <code>agents/*</code> image</span><span class="small">pin: <code>Makefile</code> → <code>PROMETHEUS_API_BASE_IMAGE_HASH ?= 1914b55</code> (v0.13.0)</span></div>
<div class="box orange" style="flex:1"><b>prometheus_agent_template → your agent</b><span class="small"><code>agent_template/Dockerfile</code></span><span class="small">default tag <code>latest</code> (compose); pin it in your <code>.env</code></span></div>
</div>
</div>

:::: grid 3
::: card
#### Not a pip dependency

{.small}
Agent `pyproject.toml` files must **not** list `prometheus_api`, a2a-sdk, starlette, or uvicorn. The image has them, and `uv sync --inexact` keeps them.
:::

::: card
#### Not git submodules

{.small}
The platform's `.gitmodules` is empty. External agents are separate repos that **register at runtime** with the platform's LiteLLM registry.
:::

::: card
#### Local venvs

{.small}
For IDE and tests outside Docker, install the same commit:

```bash {.xs}
uv pip install \
 "git+https://github.inl.gov/genesis/\
prometheus_api.git@1914b55"
```
:::
::::

---

## Where the pin lives, and what tags exist {eyebrow="Base image tags"}

:::: grid 2 gap=30px
::: col
{.sm}
| Location | Value today |
|---|---|
| platform `Makefile:22` | `1914b55` (v0.13.0 = `main`) {.hl} |
| platform `.env.example` | `#PROMETHEUS_API_BASE_IMAGE_HASH=` (keep in sync) |
| platform `docker-compose.yml` | `${PROMETHEUS_API_BASE_IMAGE_HASH:-}`, empty default |
| template `docker-compose.yml` | `${PROMETHEUS_API_BASE_IMAGE_HASH:-latest}` |
| template README / TUTORIAL | `2b3dbcf`, **stale** (v0.8.0) |
| platform `backend/` and `tests/pyproject.toml` | `rev = "1914b55…"`, matching the Makefile |
| `prometheus_api` `main` | `1914b55`, v0.13.0 (LLM tool calling, AskSage profile), the platform pin |
:::

|||

#### Tag schemes in the registry {.acc}

{.sm}
- **CI** (push to `main`): `:<YYYYMMDD>-<sha7>` and `:latest`, multi-arch (amd64 + arm64).
- **Manual** `make build-push`: `:<git short sha>`, which is the format the pins use.
- It is a **tag**, not a sha256 digest. The variable is called `…_HASH` because the tag is a commit hash.

::: callout
Bumping the SDK in the platform = changing that one Makefile line, then reading `prometheus_api/docs/agent/AGENT_MIGRATIONS.md` for everything that changed in between.
:::

::: callout warn
Running `docker compose up` in the platform **without** `make` gives an empty tag and a broken `FROM`. Always go through `make`.
:::
::::

---

## Where things live {eyebrow="Inside the repos"}

::: grid 3 gap=18px
```text {.xs}
prometheus_platform/  (dev)
├── Makefile             # up, restart, logs…
├── docker-compose.yml   # core services
├── .env.example
├── litellm_config.yaml  # LLM aliases
├── certs/INL.pem        # frontend build
├── frontend/            # React + Vite
├── backend/             # FastAPI
├── agents/
│   ├── client-agent/    # orchestrator
│   ├── form-filler-agent/
│   ├── osti-research-agent/
│   ├── synthesis-agent/
│   └── debug-agents/*/
├── tests/  # infrastructure/, system/
├── docs/   # zensical site
├── AGENTS.md · CLAUDE.md
└── README.md
```

|||

```text {.xs}
prometheus_api/  (main)
├── prometheus_api/
│   ├── agent/        # PrometheusAgent,
│   │                 #  identity, registry,
│   │                 #  artifacts, worker
│   ├── llm_client/   # LLMClient
│   ├── llm_configs/  # *.yaml profiles
│   ├── storage_client/ # DeepLynx
│   ├── credentials/
│   └── contract.py · a2a_stream.py
├── specs/  # 000–014, REQ-/BEH- IDs
├── docs/agent/  # GUIDE, MIGRATIONS
├── examples/
├── Dockerfile · Makefile
├── llm_config.example.yaml
└── .github/workflows/tests.yml
```

|||

```text {.xs}
prometheus_agent_template/
├── setup_agent.py     # scaffolder
├── TUTORIAL.md        # 1,200+ lines
├── README.md
├── success_message.txt
├── tests/test_setup_agent.py
└── agent_template/
    ├── agent.py
    ├── agent_card.json
    ├── Dockerfile · Makefile
    ├── docker-compose.yml
    ├── docker-compose.net_internal.yml
    ├── docker-compose.net_external.yml
    ├── docker-compose.linux.yml
    ├── .env.example · pyproject.toml
    ├── prompts/  workflows/
    └── tests/
```
:::

{.small}
Each subtree has its own toolchain: `uv` + `ruff` + `mypy` + `pytest` for Python, `npm` + `eslint` + `tsc` for the frontend. Never hand-edit the generated `docker-compose.agents.yml`; `make generate` rewrites it.

---

## Five kinds of branches {eyebrow="Branch roles"}

{widths="230px|330px|"}
| Branch | Cut from → merges into | Rules |
|---|---|---|
| **`main`** | merges only | Production. Never commit directly. Every merge gets a version tag (`v1.0`, `v1.1`…). If it is in `main`, it is deployable. |
| **`develop`**<br><span class="small">= <code>dev</code> in prometheus_platform</span> | integration branch | All day-to-day work flows through here. It is "what the next release will look like": not always stable, but **always buildable**. {.hl} |
| **`feature/<desc>`** | `develop` → `develop` | Short-lived, one piece of work, deleted after merge. Never touches `main`. Name it `feature/login`, `feature/mesh-qa-agent`… |
| **`release/<x.y>`** | `develop` → `main` **and** `develop` | Freezes scope. Only bug fixes, docs, and version bumps. The double merge is critical and easy to forget. |
| **`hotfix/<desc>`** | `main` → `main` **and** `develop` | The emergency lane, the only branch cut from `main`. Skipping the merge back to `develop` makes the bug resurface in the next release. |

::: callout
Only `release/*` and `hotfix/*` ever merge into `main`, and both always merge back into `develop`. Everything else flows through `develop` exclusively.
:::

---

## Which base branch do I target? {eyebrow="Applied to our repos"}

::: grid 2 gap=30px
| Repo | Integration branch | Your PR base |
|---|---|---|
| **prometheus_platform** | `dev` (default branch) | `--base dev` {.hl} |
| **prometheus_api** | `main` | `--base main` |
| **prometheus_agent_template** | `main` | `--base main` |
| agent repos (gmsh_agent…) | `main` | `--base main` |
| **genesis/hackathon** (practice + team agents) | `main` | `--base main` {.hl} |

{.small}
In the commands on the next slides, substitute `main` for `dev` when you work on a repo without a `dev` branch.

|||

#### Where we are today {.acc}

{.sm}
- Platform `dev` carries all recent work. `main` has not been updated since April 2026: the first formal release is still ahead of us.
- There are no version tags or `release/*` / `hotfix/*` branches yet. `prometheus_api` versions live in `pyproject.toml` (0.13.0) plus `docs/agent/AGENT_MIGRATIONS.md`.
- Existing branch names are mixed (`admin_setup_ui`, `fix/certs`, `task/…`, and `feat/…` in api). **New branches: `feature/<short-desc>`**.
:::

---

## You cloned `genesis` directly. Now add your fork. {eyebrow="Fork & clone conventions"}

:::: grid 2 gap=30px
```bash {.sm}
# in your existing clone of genesis/prometheus_platform
cd ~/prometheus/prometheus_platform
export GH_HOST=github.inl.gov

# 1. the org repo becomes "upstream"
git remote rename origin upstream

# 2. create your fork and make it "origin"
gh repo fork genesis/prometheus_platform --clone=false
git remote add origin \
  git@github.inl.gov:<you>/prometheus_platform.git
git fetch --all
git remote -v
#   origin    …:<you>/prometheus_platform  (push here)
#   upstream  …:genesis/prometheus_platform (PR target)

# 3. make rebase the default for pull
git config pull.rebase true
git config rebase.autoStash true
```

|||

::: card
#### Why fork?

{.small}
**Always fork the platform**: a ruleset blocks creating any branch on `genesis/prometheus_platform` except `dev`, so the PR has to go from `<you>:feature/x` to `genesis:dev`. Forking works the same way for every other genesis repo.
:::

::: card
#### Clone side by side

{.small}
`setup_agent.py` looks for `../prometheus_platform/.env` to copy secrets into your new agent. Keep this layout:

```text {.xs}
~/prometheus/
├── prometheus_platform/
├── prometheus_agent_template/
└── my-agent/            # generated
```
:::
::::

---

## Feature branch → rebase → push → PR {eyebrow="Day-to-day loop"}

```bash {.sm hl=10}
# start from the latest integration branch
git fetch upstream
git switch -c feature/mesh-qa-agent upstream/dev

# work, commit in small logical steps
git add -p
git commit -m "Add mesh quality report skill"

# stay current: replay your commits on top
git pull --rebase upstream dev

# run the local checks (next slides), then publish
git push -u origin HEAD                # first push
git push --force-with-lease            # after a rebase

# open the PR against genesis
gh pr create --repo genesis/prometheus_platform \
  --base dev --head <you>:feature/mesh-qa-agent \
  --title "Add mesh quality report skill" \
  --body-file pr.md
```

---

## Why rebase, and how to push after one {eyebrow="Day-to-day loop"}

:::: grid 3 gap=22px
::: card acc
#### Why rebase, not merge?

{.small}
Your branch stays a straight line of *your* commits on top of the current `dev`. Reviewers see only your change, the history has no "Merge branch 'dev' into …" noise, and conflicts are resolved once, commit by commit.
:::

::: card
#### `--force-with-lease`, never `--force`

{.small}
A rebase rewrites your branch, so the push must be forced. `--force-with-lease` refuses if the remote has commits you have not seen, for example a reviewer's suggestion you accepted in the web UI.
:::

::: callout warn
Force-pushing is only for **your own feature branch**. The protected branches (platform `dev`, api and template `main`) reject force-pushes, and nobody force-pushes shared branches anyway.
:::
::::

---

## When to rebase an open PR {eyebrow="Rebase and review"}

:::: grid 2 gap=30px
{.body}
The repos use **rulesets** that interact with force-pushes:

{.sm}
- **Dismiss stale approvals on push**: any new push, including a rebase, clears existing approvals.
- **Require approval of the most recent push**: whoever pushed last cannot be the approver.
- **All review threads resolved** before merge.

::: callout good
**Recommended rhythm**<br>① Rebase onto `upstream/dev` and tidy *before* requesting review.<br>② During review, push **new commits** that address comments, so reviewers see the delta.<br>③ Rebase once more only if `dev` moved and there are conflicts, then ask for a final approval.
:::

|||

#### How maintainers merge today {.acc}

{.sm}
| Repo | Allowed merge methods |
|---|---|
| prometheus_platform | merge commit, squash, rebase |
| prometheus_api | merge commit, squash (rebase-merge **off**); head branch auto-deleted |
| template, gmsh, agent-sandbox-mcp, hackathon | all three |

{.small}
In practice most PRs land as **merge commits** ("Merge pull request #N from …"). A rebased feature branch makes that merge commit clean: the history shows your commits intact, followed by one merge.
::::

---

## Commit messages people can read later {eyebrow="Commits"}

:::: grid 2 gap=30px
- **Imperative subject, under 72 characters**, capitalized, no trailing period.
- **The body explains *why***; the diff already shows what.
- One topic per commit. No "update file" or "fix bug".
- Never commit `.env`, keys, or tokens. Every repo gitignores `.env`; check `git status` anyway.
- Lockfile changed? Commit `uv.lock` with the `pyproject.toml` change.

{.small}
Based on `prometheus_platform/AGENTS.md` (subject under 72 chars, body explains why, no "update file"/"fix bug") plus the style of recent commits. The platform AGENTS.md also asks you to prefix any PR review reply written by a coding agent with 🤖.

|||

#### Real subjects from the org repos {.acc}

```text {.sm}
Add per-user chat history: list, rename,
    soft-delete, resume
Check in INL certificate and fix cert install
Drop HS256 identity support; RS256 only,
    split keys by role in compose
Configure agents by LLM profile, not by
    MODEL_NAME
Register the anl_asksage LLM config profile
```

::: callout bad
Avoid: `wip`, `fix`, `changes`, `address comments` as the only description of a change.
:::
::::

---

## Local checks per repo {eyebrow="Before you push"}

{.sm widths="280px|520px|"}
| Repo / area | Commands | Notes |
|---|---|---|
| **Your generated agent** | `uv run pytest && uv run ruff check .` | The template ships 2 tests with mocked `RequestContext` and `EventQueue`. {.hl} |
| **prometheus_platform** infra | `make test-static` | No Docker needed. `make test-integration` and `make test-system` need the stack running. |
| platform `frontend/` | `cd frontend && make install && make check` | eslint + tsc |
| platform `agents/<name>` | `cd agents/<name> && uv run pytest` | client-agent: <code class="wrap">PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -p pytest_asyncio.plugin tests</code> |
| **prometheus_api** | `make check && make test`<br>`make hooks` (once) | `check` = ruff lint + ruff format --check + mypy. The hooks run ruff on commit and mypy + unit tests on push. |
| prometheus_agent_template | `make check && make test` | Tests `setup_agent.py` itself. |
| agent-sandbox-mcp | `make check && make test` | `test-image` and `test-system` need Docker. |

::: callout warn
For the platform, the template, and the agent repos, **these local checks are the only CI**. Nothing automated runs on those PRs.
:::

---

## What runs where {eyebrow="Continuous integration"}

:::: grid 2 gap=30px
#### prometheus_api · `.github/workflows/tests.yml` {.acc}

{.small}
On a push or PR to `main`, on self-hosted runners (group `genesis`):

{.sm}
| Job (required check) | Does |
|---|---|
| Python 3.12 / 3.13 / 3.14 | `uv sync --frozen` + `pytest` in pinned uv images |
| Docker prepare | computes the tag `<YYYYMMDD>-<sha7>` and the cache URI |
| Docker amd64 / arm64 | builds the image and runs pytest *inside* it against the installed package |
| *(push only)* multi-arch | pushes the manifest `:<tag>` and `:latest` |

{.small}
Checks are strict (the branch must be up to date). There is no ruff or mypy job yet, so run `make check` yourself.

|||

#### Everything else {.acc}

{.sm}
| Repo | CI |
|---|---|
| prometheus_platform `dev` | **none**. `docs.yml` builds the docs site only on a push to `main`. |
| prometheus_agent_template | none |
| gmsh_agent, agent-sandbox-mcp | none |

::: callout warn
**Fork PRs to prometheus_api** currently get no CI runs, so the six required checks never report and a maintainer has to merge them. With write access, push your branch to the org repo and open the PR from there; otherwise ask a maintainer to re-open it from an org branch.
:::
::::

---

## Rulesets on the protected branches {eyebrow="Branch protection"}

| Branch | Approvals | Other review rules | Required checks | Push rules |
|---|---|---|---|---|
| **platform `dev`** | 1 | dismiss stale · last-push approval · threads resolved | — | no force-push, no delete {.hl} |
| **api `main`** | 1 | same, plus code-owner review (CODEOWNERS covers only `/.github`) | 6 jobs, strict | no force-push, no delete |
| **template `main`** | 1 | dismiss stale · last-push approval · threads resolved | — | no force-push, no delete |
| gmsh_agent, agent-sandbox-mcp, hackathon `main` | — | unprotected | — | — |
| platform `main` | — | its ruleset targets no branch yet | — | — |

:::: grid 3
::: card
#### PR required

{.small}
No one pushes to `dev` or api/template `main` directly, not even admins (no bypass actors).
:::

::: card
#### Someone else approves

{.small}
You cannot approve your own PR, and the last pusher cannot approve either. Pair up with another team for reviews.
:::

::: card
#### No PR templates

{.small}
There is no template in any repo, so use the structure on the next slide.
:::
::::

---

## A description reviewers can act on {eyebrow="Opening a PR"}

::: cols 1.3fr 1fr
```markdown {.sm}
JIRA: PPLT-123

## What
Add a `mesh_quality_report` skill that reads an
Exodus artifact and reports scaled Jacobian and
aspect-ratio histograms.

## Why
Meshes from `geometry_meshing` go to MOOSE
unchecked; bad elements fail late.

## How it was tested
- `uv run pytest` (6 passed), `uv run ruff check .`
- Local platform: "check the mesh I just made"
  routes to the skill; report artifact renders.

## Config / environment changes
- New env var `MESHQA_MAX_ELEMENTS` (default 2e6)
- Base image: PROMETHEUS_API_BASE_IMAGE_HASH=1914b55
```

|||

- **Title**: an imperative sentence, like the commit subject ("Add…", "Fix…", "Stop…").
- **Reference the JIRA task** (`PPLT-…`) at the top of the description.
- **Small and focused.** One topic. Split refactors from behavior changes.
:::

---

## More PR conventions {eyebrow="Opening a PR"}

::: grid 2 gap=30px
- List the **commands you ran**, and any env var, Docker image, credential, or DeepLynx behavior change (`prometheus_api/AGENTS.md`).
- **prometheus_api API changes**: bump the version (`make bump-minor`/`bump-patch`), add a section to `docs/agent/AGENT_MIGRATIONS.md`, and update `specs/` with tests that cite the REQ IDs.
- UI change? Add a screenshot.
- Open as **draft** (`gh pr create --draft`) while it is still in progress.

|||

#### Handy commands {.acc}

```bash {.xs}
gh pr view --web          # open in browser
gh pr checks              # CI status (api only)
gh pr ready               # draft → ready
```
:::

---

## What reviewers look for, and how to respond {eyebrow="Code review"}

:::: grid 2 gap=24px
::: card
### As an author

{.sm}
- Reply to **every** thread. "Fixed in 8e46a68: …" with the commit SHA and a sentence of explanation.
- Disagree with reasons. Maintainers push back too, sometimes with a table of cases.
- Resolve threads only when the reviewer is satisfied, or after replying.
- Accepted a GitHub suggestion in the web UI? `git pull --rebase` before your next push.
:::

::: card
### As a reviewer

{.sm}
- Be concrete: file:line, the scenario that breaks, ideally a failing test.
- Check the tests enforce what they claim. In the api repo, reviewers check that tests citing a `REQ-…` ID actually test it.
- Check the lockfile, the version bump, and the migration note.
- Separate "must fix" from "nit".
:::
::::

---

## The project stance, and the bar {eyebrow="Code review"}

:::: cols 1fr 1fr gap=24px
::: card
### Project stance

{.tiny}
From the Prometheus project philosophy.

{.sm}
- Experimental project: **breaking changes are fine**.
- No backward-compatibility shims, deprecation warnings, or workarounds. Fix root causes.
- When docs and code disagree, fix the docs in the same PR.
- Agent-authored review text is marked with 🤖.
:::

|||

::: callout
A real example: platform PR #98 had about 10 inline findings, each reproduced with a small test. The author answered each one with the fixing commit. That is the bar.
:::
::::
