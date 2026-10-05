# Hackathon challenge: the Table & Plot agent

Every team builds the same thing: **one Prometheus agent with at least two skills.**

| Skill | Does |
|-------|------|
| **Extract a table** | Given a markdown document (uploaded in the chat) and a description of the table the user wants ("the table with population data"), find that table, parse it, and emit it as a **table artifact**. |
| **Plot tabular data** | Given tabular data (a table artifact from the first skill, *or* an uploaded CSV file) and the columns to plot, emit a **plot artifact** (a PNG image that renders in the chat). |

You have about 4–5 hours. Then it's demo time.

## What you get now

- `practice/lunar_cheese_annual_report.md`: a markdown report with several captioned tables.
- `practice/cheese_mouse_sightings.csv`: a plain CSV file.
- An example prompt, used after uploading the markdown file:

  > Extract the table with the population data and plot the population of Brie Basin versus year.

## What happens at demo time

You get a **new markdown file you have not seen**, a new CSV file, and two or three prompts. They test:

1. **Finding the right table by its caption.** Users refer to tables by what the caption says, not by number, and not always in the same words.
2. **Matching column names intelligently.** Users say "temperature" and "time"; the file may say something terser, with symbols and units.
3. **Skill separation and follow-up questions.** A user may upload a file and just say "plot this". Your agent should ask which columns to plot, offering the real column names, instead of guessing or failing.

The new files follow the same conventions as the practice file: GitHub-flavoured markdown tables, a bold caption directly **above** each table, units in the column headers, and prose between the tables. Expect the unexpected in the details: thousands separators, missing values, non-numeric columns, symbols.

## Requirements (the gate)

1. Built from `prometheus_agent_template`; a `PrometheusAgent` subclass.
2. At least **two skills** in `agent_card.json`, with unique, team-prefixed skill IDs and card name.
3. Registers with your local platform; visible under `/agents`.
4. Natural-language requests in the chat are **routed by the orchestrator** to the right skill.
5. The extract skill emits a table artifact; the plot skill emits an **image** artifact that renders in the chat.
6. `uv run pytest` and `uv run ruff check .` pass.
7. The code is in a repo with a PR reviewed by someone outside the team.

## Platform prerequisites

- **DeepLynx must be configured** (local or shared instance). Chat uploads are stored there, and a PNG artifact needs DeepLynx to render (`send_deeplynx_artifact`).
- Add `matplotlib` (and anything else you import) to your agent's `pyproject.toml`; use the `Agg` backend.
- LLM calls: pick a provider with `LLM_CONFIG_PROFILE` (`inl_litellm`, `amsc`, or `anl_asksage`) and its key in your agent's `.env`, then use `self.llm_client(context)` with the flavor that fits each call (`small` for cheap classification, `medium`/`large` for matching, `vision` to check a plot).

See the Day 1 decks (`index.html`) for everything else.
