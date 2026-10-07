# Hackathon repository

Participants of the Prometheus agent hackathon put their agents here. Most of them are new to
Prometheus. Teach while you help.

## Layout

- `practice/<you>/`: Day 1. Only `agent.py`, `agent_card.json`, and `README.md` of the agent
  in `../hello-<you>/`, for the practice PR.
- `agents/<team_name>/`: Day 2. One folder per team.
- `hollowmere_almanac.md`: the practice file for Day 2. Do not edit it.
- `../prometheus_platform/` and `../prometheus_agent_template/`: the platform and the template,
  next to this repository. They are read-only for the hackathon.
- `.claude/skills/how/references/`: the knowledge base (KB). Start at `index.md`. Every skill
  obeys `conventions.md`.

## Skills

There are three skills. Say what you want in your own words; the skill finds the right steps.

- `/create-agent [what you want]`: build your agent. It sets up a new agent that runs and is
  registered, adds a platform feature (files, artifacts, forms, LLM calls), or improves the
  agent card so that the orchestrator calls the agent.
- `/diagnose [what is wrong]`: find and fix what does not work. It fixes an error, checks that
  the laptop is ready (the homework), or explains what the orchestrator did in one chat turn.
- `/how [question]`: learn. It answers a question from the KB and the code, or makes an HTML page
  with diagrams that explains one concept.

## Rules

1. Teach. Explain each change in one or two lines. Ask before an edit to more than one file.
   Point to the skill that fits the request. When the user says "skip the quiz", stop the
   check questions for the session.
2. Write the plumbing: helper calls, card fields, the skill dispatch, the follow-up form wiring,
   and test scaffolds with mocks. Leave the domain logic as a TODO with hints, unless the user
   asks you to write it.
3. Never show a secret, and never ask for one in the chat. Never run `cat .env`, `env`,
   `printenv`, `docker compose config`, `docker inspect`, `curl -v`, or `set -x`. Check a key
   with `grep -c '^KEY=.' <file>`. Never commit a `.env` file. More in `conventions.md`.
4. Edit only the user's own agent folder and `.explainers/`. Never edit `.claude/`, another
   participant's or team's folder, or `hollowmere_almanac.md`. In the platform folder, change
   only the untracked `.env` and `docker-compose.override.yml`, and only after a yes.
5. Start a fresh chat conversation for each test of an agent.
6. When a doc disagrees with the code, the code is correct. Say so, and name a mentor
   (`mentors.md`).
7. A personal skill in `~/.claude/skills/` with the same name as a skill here runs instead of
   it. Tell the user to rename the personal skill for the hackathon.
8. The Linux and WSL commands in the skills are not verified yet. Say so when you use one.
