---
up: []
related: []
created: {{date}}
---

# Open Item

An actionable unit of work (a to-do or a dated commitment) **owned by exactly one note** and merely *viewed* everywhere else — written as a Markdown task line with Dataview inline fields so it is both live-queryable in Obsidian and regex-parseable by `open-items.py`.

- Schema: `- [ ] <desc> [status:: open|blocked|done] [due:: <YYYY-MM-DD>?] [raised:: <YYYY-MM-DD>]`.
- `status::` — `open` · `blocked` · `done` (a checked box implies `done`); `due::` — presence promotes the item to a **Deadline**; `raised::` — stamped once, drives aging.
- The day note and the open-items ledger are **views**; the owning effort/project note is the single source of truth.

**Sources:** [open_item.md](../../ideaVerse/atlas/concepts/open_item.md)
