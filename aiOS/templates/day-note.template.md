---
up: []
tags: []
related: ["[[day-note.runbook]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: []
---

> **Day note for {{date}}** — `ideaVerse/calendar/days/{{date}}.md`. One file per working day: the raw daily log and a primary source that `wiki-sync` mines. Capture what happened today, keep it source-traceable, fill the sections that apply and delete the rest. **Summarise, don't transcribe.**
>
> Frontmatter: `tags` = topical; `related` = `[[wikilinks]]` to projects, efforts, people, adjacent days; `sources` = every URL / ticket / link this note draws on.

> [!tldr] At a glance — {{date}}
> **✅ <n> shipped · 🔴 <n> waiting on others · ⏳ <n> active · 📅 <n> deadline (<Nd>)**
>
> - **Shipped:** <what landed today, one clause each>.
> - **🔴 Waiting:** <items blocked on someone else, and who>.
> - **⏳ Resume here:** <the single most important next action — the thing future-you needs first>.
> - **📅 Deadline:** <nearest dated commitment — date + days out>.

# Deadlines

_Dated commitments = [[open_item|open items]] carrying a `[due::]`. One checkbox each: glyph · what · the **date** · the `[[project]]` · schema fields. Tick when met and record the outcome. Wrap in a `[!danger]` callout so it pops._

> [!danger] Dated commitment
> - [ ] ⏳ <commitment> — **<YYYY-MM-DD>** ([[project]]). [status:: open] [due:: <YYYY-MM-DD>] [raised:: <YYYY-MM-DD>]

# Tasks

_Actionable to-dos. Every task **or** deadline raised anywhere today is lifted up here (or to Deadlines) — never left buried in a chat summary. Each is an [[open_item]]: a status glyph (✅ done · 🔴 blocked · ⏳ open) + inline schema `[status:: open|blocked|done] [due:: <date>?] [raised:: <date>]`. `raised::` is stamped once when the item first appears and never changed._

> [!warning] Waiting on others / blocked
> - 🔴 <blocked item> — <who / what it waits on>.

- [x] ✅ <shipped task> ([[project]] if relevant). [status:: done] [raised:: <YYYY-MM-DD>]
- [ ] ⏳ <active task>. [status:: open] [raised:: <YYYY-MM-DD>]
- [ ] 🔴 <blocked task>. [status:: blocked] [raised:: <YYYY-MM-DD>]

> [!note] Standing backlog lives in its owning effort/project note
> Recurring/unowned items live in a standing effort note, not here. Reference them; don't re-type them. The live cross-note view is the [open-items ledger](../../open-items.md) (`open-items.py`).

# Chats / discussions — {{date}}

_Summary of the day's relevant discussions, banter filtered. One subsection per topic/thread. Give the gist and the decision **and who made it** — not a message-by-message replay. Route any task/deadline up to the sections above; link the `[[project]]` / `[[note]]`._

## <topic / thread>

<short summary; preserve the actual decision wording and attribute it>

# <Work / topic sections>

_Free-form, single-purpose headings for the substance of the day (Release, Resolved — `<issue>`, Design handoff, Grilling — `<topic>`, etc.)._

# IdeaVerse / conventions added today

_Anything that should outlive the day: new conventions, note updates, wiki compiles. Link the notes touched._

-

---

> **Building this note:** see [[day-note.runbook]] for the full how-to. In short: fill the at-a-glance callout, lift every task/deadline into its own section with glyph + [[open_item]] schema, summarise discussions (gist + decision + who), keep it source-traceable. After writing, re-run `python3 ideaVerse/aiOS/scripts/open-items.py --today {{date}}` to refresh the [open-items ledger](../../open-items.md).
