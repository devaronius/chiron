---
up: []
tags: ["ideaverse", "day-note", "process"]
related: ["[[day-note.runbook]]", "[[day-note.template]]"]
created: {{date}}
updated: {{date}}
sources:
  - aiOS/templates/day-note.template.md
  - aiOS/templates/day-note.runbook.md
aliases: ["Open Item", "open items", "open-item", "action item", "carried backlog", "standing backlog"]
---

# Open Item

**Open item** — a single actionable unit of work (a to-do or a dated commitment) that is *owned by one note* and merely *viewed* everywhere else. An open item lives in the `[[effort]]`/`[[project]]` note it belongs to (or a standing "ops" effort note if it belongs to none); the day note and the global open-items ledger render **views** over those owning notes — they never re-declare the item. This avoids the habit of re-typing a "carried backlog" block into every day note, which drifts and can't be ticked.

An open item is written as a Markdown task line carrying **Dataview inline fields**, chosen so the same line is queryable live in Obsidian *and* regex-parseable by `open-items.py`:

```
- [ ] <description> [status:: open] [due:: 2026-07-31] [raised:: 2026-07-06]
```

- **`status::`** — one of `open` · `blocked` · `done`. `blocked` is distinct from `open` so the day-note "at a glance" header and callouts can surface blockers separately. A checked box (`- [x]`) and `status:: done` mean the same thing; keep them consistent.
- **`due::`** *(optional)* — the ISO date of a dated commitment. Presence of `due::` is what promotes an open item into a **Deadline** view. Omit for undated to-dos.
- **`raised::`** — the ISO date the item was first added, auto-stamped once and never changed. This is the field that makes aging computable (`today − raised`).

Priority and owner are intentionally **not** required fields — keep priority informal in the description text (`owner::` is supported by the parser but optional).

## Not to be confused with

- **[[day-note.template|Task (day-note section)]]** — the day note's `# Tasks` heading is a *rendered view* of open items owned elsewhere, not a place where tasks are born. An item typed only under a day's `# Tasks` with no owning note is the anti-pattern this concept removes.
- **Deadline** — not a separate entity: a **Deadline is an open item that carries a `due::` date**. The day note's `# Deadlines` view is simply the `due::`-bearing subset. Don't model deadlines as a parallel list with its own source of truth.
- **Effort / project** — the *owner* of open items, not an item itself. An effort note holds many open items plus its decision log and prose; the item is the tick-able line, the effort is its home.

## Decision

- **Context:** open items tend to get re-typed as prose across day notes, so status drifts, items can't be ticked, and there's no single place to update one.
- **Decision:** one source of truth per item — the owning `[[effort]]`/`[[project]]` note (or a standing ops note for strays) — expressed as a task line with `[status::] [due::] [raised::]` inline fields. Day note and global ledger are generated/queried **views**.
- **Consequences:** every open item must be owned by *some* note; stray/ops items get a standing effort note so nothing is orphaned. Views are rendered two ways (Dataview live in Obsidian + `open-items.py` static fallback), so the schema must stay regex-clean.

**Sources:** `aiOS/templates/day-note.template.md`, `aiOS/templates/day-note.runbook.md`.
