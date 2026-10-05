# Writing slides in Markdown

Each deck is one file here: `slides/NN-name.md`. Run `make build` to turn every deck
into `NN-name.html` (and refresh the deck list in `index.html`), then `make check`
for the layout check and `make pdf` for PDFs. Never edit the generated `NN-*.html`.

```
make build                          # all decks
make build DECKS=slides/04-agent-template.md
make check                          # overlaps / overflow, must report 0 issues
```

## The file

```markdown
---
title: Building an Agent             # browser tab title
footer: Day 1 · Building an agent    # footer text on every slide
accent: agt                          # welcome|gh|dep|agt|dry|team|judge, or "#rrggbb"
index:                               # the deck's entry in index.html
  time: '2:45'
  heading: Building an agent
  color: var(--orange)
  blurb: One line describing the deck.
css: |                               # optional extra CSS for this deck
  .award { … }
---

# First slide …

---

## Second slide …
```

Slides are separated by a line containing only `---`.

## Kinds of slides

| You write | You get |
|---|---|
| `# Title {.title kicker="Day 1 · 2:45 pm" pills="All participants \| 45 min"}` + a paragraph | title page with logos; the paragraph is the subtitle |
| `# Heading {.section num=A}` + a paragraph | interstitial page (big number, heading, lede) |
| `## Heading {eyebrow="The code you write"}` | normal slide with eyebrow and heading |
| a `> text` line right after a `##` heading | the lede (intro sentence under the heading) |

**Mode switches.** Put `.bonus` or `.appendix` on a section heading
(`# Appendix: reference {.section .appendix num=A}`) and every following slide
becomes a bonus or appendix slide (striped, numbered "A n / m"). `.main` switches back.

**Slide options** on the `##` heading, all optional:

- `.nofit`: no auto-sizing
- `.nofoot`: no footer
- `style="gap:10px"`: inline style on the slide
- `content="center"`: extra classes on the content area
- `content-style="…"`: inline style on the content area

**Speaker notes**: a paragraph starting with `Note:` (shown with the `N` key).

## Text, lists, tables

Normal Markdown: `**bold**`, `*italic*`, `` `code` ``, `[link](url)`, lists, tables.

- Put a class line **before** a block to style it: `{.small}` before a paragraph,
  `{.sm}` / `{.xs}` / `{.check}` before a list, `{.sm}` / `{.xs}` / `{.nw}` / `{.wrap-code}` before a table.
- Lists get the deck's bullet style and tables the deck's table style automatically.
- A table row ending in `{.hl}` is highlighted: `| make up | build and start {.hl} |`.
- Column widths: put `{widths="230px||330px"}` before the table (empty = automatic).

## Code

````markdown
```python {.sm hl=4-5}
from prometheus_api.agent import PrometheusAgent
…
```
````

- The language name sets the highlighting: `python`, `bash`, `json`, `yaml`, `markdown`, `docker`, or `text`.
- `{.sm}` / `{.xs}` sets a smaller font.
- `hl=4-5` highlights lines (comma-separated ranges also work).
- Placeholders like `<you>` and `<team_name>` are colored automatically, except in comments.

## Layout blocks

Blocks start with `:::` plus a name and end with `:::`. To nest one block in another,
give the **outer** one more colons (`::::`).

| Block | Use |
|---|---|
| `::: cols 1.35fr 1fr` … `\|\|\|` … `:::` | columns with the given widths; a line `\|\|\|` starts the next column (optional `gap=24px`) |
| `::: grid 3` | equal columns (2–5). Children are cards or callouts, or parts separated by `\|\|\|` |
| `::: card acc tag="Skill 1"` | a card (`acc` = colored); its content is normal Markdown, usually starting with `### Heading` |
| `::: callout warn` | a colored box: no class (accent), `warn`, `bad`, `good`, `info` |
| `::: steps` | numbered steps; each `#### Heading` + text is one step |
| `::: takeaways` | big numbered points; each `### Heading` + text is one point |
| `::: agenda` | a list of `- time \| title \| description`, with `{.now}` at the end to highlight a row |
| `::: flow` | a one-row box diagram (below) |
| `::: col` | a column of blocks |
| `::: anything classes` | a plain `<div class="anything classes">` for other CSS components |

Example:

```markdown
:::: grid 3
::: card acc tag="Skill 1"
### Extract a table
Find it **by its caption** and publish it as a table artifact.
:::
::: card
### Plot it
…
:::
::::
```

### Flow diagrams

```markdown
::: flow
- [gray] **Chat upload**
- ->
- [teal flex=1.2] **DeepLynx** | stores the file
- -> table id {w=90}
- [orange] **Your skill** | ~params["document_artifact_id"]
:::
```

- `[color flex=…]` starts a box. The colors are `navy`, `sky`, `teal`, `green`, `orange`, `crimson`, `violet`, `gray`, and optionally `dash` for dashed. `flex` sets the relative width.
- After the bold title, `|` separates further lines. These are small text by default, `=text` is normal size, and `~text` is monospace. Flow text cannot contain a literal `|`; use raw HTML for such a box.
- `->` is an arrow, with an optional label and `{w=90}` for its width in px. `<-` points left.

## Anything else: raw HTML

Any HTML block passes through unchanged. Use it for multi-row diagrams, SVGs, images,
or one-off layouts. Inside a raw HTML block a line containing only `<!---->` keeps an
empty line (an empty line would end the block).

## Tools

- `tools/build.py`: Markdown → HTML (used by `make build`).
- `tools/html2md.py`: the one-time HTML → Markdown converter used for the migration.
- `tools/check_layout.py`, `tools/export_pdf.py`, `tools/sheet.py`, `tools/compare.py`: checking, PDFs, contact sheets, before/after comparison.
