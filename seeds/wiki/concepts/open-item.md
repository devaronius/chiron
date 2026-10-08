---
up: []
related: []
created: {{date}}
---

# Open Item

An actionable unit of work (a to-do or a dated commitment) **owned by exactly one note** and merely *viewed* everywhere else — written as a Markdown task line with Dataview inline fields so it is both live-queryable in Obsidian and regex-parseable by `open-items.py`.

- Schema: `- [ ] <desc> [status:: open|blocked|done] [assignee:: <who>?] [due:: <YYYY-MM-DD>?] [raised:: <YYYY-MM-DD>]`.
- `status::` — `open` · `blocked` · `done` (a checked box implies `done`); `due::` — presence promotes the item to a **Deadline**, and it doubles as the ask-again date; `raised::` — stamped once, drives aging.
- `assignee::` — **who must act next**, and the only thing that routes the item to a lane: `agent` (runs unattended once *ready*), your own handle (surfaced when *ripe*), another name (silent), or absent (*unrouted*, surfaced every session). `status:: blocked` outranks the lane, because unblocking is a human act.
- **Ripe ≠ ready.** An undated item is never ripe for the human digest, but is ready for the agent queue immediately; an unparseable `due::` is ripe *and* not ready, so a typo cannot authorise unattended work.
- The day note and the open-items ledger are **views**; the owning effort/project note is the single source of truth.

**Sources:** [open_item.md](../../ideaVerse/atlas/concepts/open_item.md)
