---
title: Judging & Awards
footer: Day 2 · Judging & awards
accent: judge
css: "  .award { background: #fff; border: 1px solid var(--rule); border-top: 6px solid var(--acc); border-radius: 12px; padding: 22px 24px; display: flex; flex-direction: column; gap: 9px; min-width: 0; min-height: 250px; }\n  .award .ic { font-size: 52px; line-height: 1; }\n  .award h4 { font-size: 26px; }\n  .award .for { font-family: var(--mono); font-size: 14px; letter-spacing: .06em; text-transform: uppercase; color: var(--acc-ink); font-weight: 600; }\n  .award p { font-size: 19px; line-height: 1.4; color: var(--ink-2); }\n  table.score td { height: 34px; }"
index:
  time: Day 1 + 2
  heading: Judging &amp; awards
  color: var(--teal)
  blurb: 'For participants: what to submit, the seven must-haves, the hidden test (40 points), its rules, the rubric, stretch bonuses, the awards, the schedule.'
---

# Judging & awards {.title kicker="Agent developer hackathon · Day 2" pills="All teams | show this on Day 1 and again before demos"}
How the Table & Plot agents are evaluated: the gate, the hidden test with a file nobody has seen, the rubric, stretch bonuses, and the awards.

---

## How judging works {eyebrow="Overview"}

:::: grid 4
::: card acc
<div class="kpi"><span class="v">1</span><span class="l">pass / fail</span></div>

### Gate

{.small}
Seven must-haves. Agents that pass all of them are ranked for the main prizes; everyone can win a category award.
:::

::: card acc
<div class="kpi"><span class="v">2</span><span class="l">40 points</span></div>

### Hidden test

{.small}
A new markdown file, a new CSV, and three prompts. Scored item by item while the judges watch.
:::

::: card acc
<div class="kpi"><span class="v">3</span><span class="l">60 points</span></div>

### Rubric

{.small}
Skill design, plot quality, robustness, engineering, demo. Each scored 1–5 by every judge.
:::

::: card acc
<div class="kpi"><span class="v">4</span><span class="l">+10 max</span></div>

### Stretch bonus

{.small}
+2 for each stretch goal shown working, capped at +10.
:::
::::

:::: grid 2
::: callout info
**Final score** = hidden test (40) + the average of the judges' rubric points (60) + stretch bonus (up to 10) − penalties. Ties are broken by the hidden-test score, then *Robustness*.
:::

::: callout
**Judges**: \[names\]. A mentor who wrote code for a team does not score that team. Judges' decisions on the awards are final; People's Choice is by participant vote.
:::
::::

Note: Fill in judge names. Weights can be adjusted; hidden test + rubric must still add to 100.

---

## By \[time\] on Day 2, each team provides {eyebrow="What to submit"}

:::: grid 2 gap=30px
| Item | Details |
|---|---|
| **PR links** | The team's PRs to `genesis/hackathon` (`agents/<team_name>/`), at least one reviewed |
| **Commit SHA** | The exact commit being judged; later commits are not scored |
| **Card name + skill IDs** | As registered, e.g. `neutron-table-plot-agent` / `neutron_extract_table`, `neutron_plot_table` |
| **Demo machine** | The laptop with your platform running, DeepLynx configured, and your agent registered |
| **README** | What each skill does, how to run it, env vars, known limits |

|||

::: card
#### House rules

{.sm}
- Code must be written during the hackathon. Libraries and existing org code are welcome, with attribution in the README.
- The test runs on **your** local platform (`idaholab/prometheus_core` `devel` at the commit announced on Day 2, \[SHA\]; agents on the `latest` base image), in a fresh conversation, with the judges at the keyboard.
- Any LLM profile is allowed. Say which one you use.
- No changes to the platform itself are needed or scored.
- Teams can win at most **two** awards.
:::

::: callout bad
**Penalties**: a secret committed to the repo (−10); code special-cased for the hidden file after seeing it (disqualification from the main prizes); the demo runs code other than the submitted SHA (−10).
:::
::::

Note: Set the submission deadline, a place to collect submissions, and the platform SHA. Gate #7 relies on the genesis/hackathon ruleset on main; check it exists.

---

## Seven must-haves {eyebrow="Stage 1 · the gate"}

:::: grid 2 gap=30px
1. Built from the agent template (`prometheus_core/agent-template`); a `PrometheusAgent` subclass
2. At least **two skills** (extract, plot) with team-prefixed IDs
3. Registers with the platform; listed under `/agents`
4. Natural-language requests are **routed by the orchestrator**
5. Extract emits a table artifact; plot emits an **image that renders**
6. `uv run pytest` and `uv run ruff check .` pass
7. A PR **approved by someone outside the team**

|||

::: callout
Judges check each one on your demo machine with the practice file, and in a fresh clone of your submitted commit. Try #6 there first; install the SDK before `uv run pytest`.
:::

::: callout warn
Miss the gate and you still take the hidden test, get feedback, and can win category awards, but you are not ranked for the main prizes.
:::
::::

---

## A new file, three prompts, 40 points {eyebrow="Stage 2 · the hidden test"}

::: col
{.body}
Judges bring a **markdown file and a CSV file nobody has seen**, written with the same conventions as the practice file. In a fresh conversation they upload the files and type the prompts exactly as written on their sheet.

{widths="||70px"}
| Test | What is checked | Pts |
|---|---|---|
| **1 · Find the table** | the right table, chosen by caption · the right columns · an image that renders, axes labelled with units | 15 |
| **2 · Match columns** | the right table · symbols and abbreviations mapped to the user's words · an image that renders | 12 |
| **3 · Plot this file** | the plot skill handles the CSV directly · it asks which columns to plot (more points for offering the real names) · it plots after the answer | 13 |
:::

---

## Rules of the test {eyebrow="Stage 2 · the hidden test"}

:::: col
::: card acc
#### Rules of the test

- The team may not touch the keyboard or explain the prompt to the agent.
- Each prompt gets **one** attempt; follow-up questions are answered by the judge. "Offers the real names" counts only for the agent's dropdown, not a free-text question from the orchestrator.
- An upload that fails on the platform side (the chat says the file "was not stored as a platform artifact") is redone in a fresh conversation and doesn't use the attempt.
- A timeout of 3 minutes per prompt.
- Plotting extra series alongside the right one, or asking a sensible clarifying question, is fine.
- Plotting the wrong columns or the wrong table scores zero for that item, even if the plot looks good.
:::

::: callout
The prompts and files are revealed to everybody after the last team's test.
:::
::::

---

## Five criteria, 60 points {eyebrow="Stage 3 · the rubric"}

{widths="330px|110px|"}
| Criterion | Weight | What the judges look for |
|---|---|---|
| **Skill design & agent card** | 15 | Clean separation into skills; descriptions and `usage_notes` that route reliably; schemas with described properties; artifacts passed between skills, not data in prompts {.hl} |
| **Plot quality** | 10 | Axis labels with units, a meaningful title (from the caption), a legend for multiple series, sensible chart type, readable at chat size |
| **Robustness** | 10 | Judges try off-nominal requests: a table that doesn't exist, a text-only column, a wrong file type. Clear messages or follow-up questions, no crashes {.hl} |
| **Engineering quality** | 15 | Tests for parsing, matching, and plotting (with the LLM mocked); clean commits and PRs; README; no secrets; minimal `pyproject.toml` |
| **Demo & communication** | 10 | A clear 5-minute story: the approach, the trade-offs (regex vs LLM, where matching happens), a look at the code, what didn't work |

{.small}
Each judge scores every criterion from 1 to 5. Points = score ÷ 5 × weight. Example: a 4 on Skill design gives 12 of 15 points.

---

## +2 per stretch goal shown working, up to +10 {eyebrow="Stage 4 · stretch bonus"}

{widths="40px|480px|"}
| # | Stretch goal | Counts when the judges see… |
|---|---|---|
| 1 | Live status updates (`"streaming": true`) | progress messages in the UI during the run ("Found 4 tables…", "Plotting T \[K\] vs t \[min\]…") |
| 2 | LLM matching with tool calling or structured output | a bounded tool loop or a forced tool call in the code, and its effect in the hidden test |
| 3 | Asks for missing columns, offering the real names | a dropdown with the file's column names in the follow-up form |
| 4 | A workflow YAML chaining extract → plot | the workflow started by a natural-language request, with no follow-up questions |
| 5 | A third useful skill | e.g. `list_tables`, `describe_table`, or `convert_units`, routed from a natural-language request |
| 6 | A 5-minute demo: conversation, plot, code walkthrough | all three parts within the time limit |

::: callout
Bonus points reward breadth; the hidden test rewards robustness. Get the 40 first.
:::

---

# The awards {.section num="🏆"}
Best in Show plus a set of "best agent in…" categories. Every team is eligible for the category awards, gate or no gate.

---

## Ranked on the score {eyebrow="Main prizes"}

::: grid 3 gap=22px
<div class="award"><span class="ic">🏆</span><span class="for">Best in show</span><h4>Prometheus Prize</h4><p>Highest final score among teams that passed the gate.</p></div>

|||

<div class="award"><span class="ic">🥈</span><span class="for">Runner-up</span><h4>Second Stage Award</h4><p>Second-highest final score among teams that passed the gate.</p></div>

|||

<div class="award"><span class="ic">🗳️</span><span class="for">Participant vote</span><h4>People's Choice</h4><p>Every participant gets one vote, not for their own team. Counted during judges' deliberation.</p></div>
:::

::: callout
Main prizes follow the score. The categories on the next two slides are chosen in the judges' discussion, using what they saw in the hidden test, the demos, and the repos.
:::

---

## Category awards (1/2) {eyebrow="Best agent in…"}

::: grid 3 gap=18px
<div class="award"><span class="ic">🔍</span><span class="for">Best table finding</span><h4>Table Detective</h4><p>Found the right table every time, however the judges described it.</p></div>

|||

<div class="award"><span class="ic">🧭</span><span class="for">Best column matching</span><h4>Column Whisperer</h4><p>Knew that "temperature" was <code>T [K]</code> and that <code>t</code> is not <code>T</code>.</p></div>

|||

<div class="award"><span class="ic">📈</span><span class="for">Best plot</span><h4>Show Me the Plot</h4><p>The plot you'd put straight into a report: labels, units, title, legend, and taste.</p></div>

|||

<div class="award"><span class="ic">💬</span><span class="for">Best follow-up question</span><h4>Good Question</h4><p>Asked exactly what it needed, offering the right choices, and nothing more.</p></div>

|||

<div class="award"><span class="ic">🎯</span><span class="for">Best agent card</span><h4>Orchestrator's Pet</h4><p>The orchestrator routed every request to the right skill, for every phrasing.</p></div>

|||

<div class="award"><span class="ic">🛑</span><span class="for">Best failure handling</span><h4>SCRAM Award</h4><p>Shut down safely when the judges tried to break it: clear messages, no stack traces.</p></div>
:::

---

## Category awards (2/2) {eyebrow="Best agent in…"}

::: grid 3 gap=18px
<div class="award"><span class="ic">⚡</span><span class="for">Fastest correct run</span><h4>Speed of Light</h4><p>The shortest time from prompt to correct plot across the hidden test.</p></div>

|||

<div class="award"><span class="ic">🛡️</span><span class="for">Best engineering hygiene</span><h4>Defense in Depth</h4><p>The best tests, reviews, and README: the agent a maintainer would merge first.</p></div>

|||

<div class="award"><span class="ic">💙</span><span class="for">Best demo</span><h4>Cherenkov Glow</h4><p>The brightest 5 minutes: a clear story, honest trade-offs, a crowd that wants to try it.</p></div>

|||

<div class="award"><span class="ic">🧪</span><span class="for">Most ambitious extra</span><h4>Moonshot</h4><p>The boldest third skill or feature, even if not everything worked.</p></div>

|||

<div class="award"><span class="ic">🐛</span><span class="for">Best debugging story</span><h4>Half-Life Award</h4><p>The team that lost half its day to a bug and came back. Tell us the story in the demo.</p></div>

|||

<div class="award" style="background:var(--panel)"><span class="ic">✨</span><span class="for">Judges' discretion</span><h4>Special mention</h4><p>Judges may skip a category if no team fits it, or add one for something nobody expected.</p></div>
:::

---

## Schedule for demos and awards {eyebrow="Day 2 end" content-style="gap:0"}

::: agenda
- \[time\] | Code freeze and submissions | PR links and commit SHA in `genesis/hackathon`, card name and skill IDs, README
- \[time\] | Gate checks | Judges and mentors verify the must-haves on each demo machine with the practice file
- \[time\] | Per team: 5 min demo + hidden test (≈ 10 min) | The team demos with the practice file, then the judges run the hidden prompts and two off-nominal requests
- \[time\] | Reveal · People's Choice vote · deliberation | The hidden files and prompts are shown to everybody; about 20 minutes
- \[time\] | Awards | Category awards first, then People's Choice, runner-up, and Best in Show
- \[time\] | What happens next | How the best agent gets reviewed and brought into the platform
:::
