---
up: []
kind: behaviour
tags: ["ideaverse", "day-note", "process"]
related: ["[[day-note.runbook]]", "[[day-note.template]]"]
created: {{date}}
updated: {{date}}
sources:
  - aiOS/templates/day-note.template.md
  - aiOS/runbooks/day-note.runbook.md
aliases: ["Open Item", "open items", "open-item", "action item", "carried backlog", "standing backlog", "lane", "assignee"]
---

# Open Item

**Open item** — a single actionable unit of work (a to-do or a dated commitment) that is *owned by one note* and merely *viewed* everywhere else. An open item lives in the `[[effort]]`/`[[project]]` note it belongs to (or a standing "ops" effort note if it belongs to none); the day note and the global open-items ledger render **views** over those owning notes — they never re-declare the item. This avoids the habit of re-typing a "carried backlog" block into every day note, which drifts and can't be ticked.

An open item is written as a Markdown task line carrying **Dataview inline fields**, chosen so the same line is queryable live in Obsidian *and* regex-parseable by `open-items.py`:

```
- [ ] <description> [status:: open] [assignee:: agent] [due:: 2026-07-31] [raised:: 2026-07-06]
```

- **`status::`** — one of `open` · `blocked` · `done`. `blocked` is distinct from `open` so the day-note "at a glance" header and callouts can surface blockers separately. A checked box (`- [x]`) and `status:: done` mean the same thing; keep them consistent.
- **`assignee::`** — **who must act next**, and the only thing that routes an item to a lane: `agent`, your own handle (`assignees.self` in `aios.config.json`), any other name, or absent. See the Decision below.
- **`due::`** *(optional)* — the ISO date of a dated commitment. Presence of `due::` is what promotes an open item into a **Deadline** view, and it doubles as the **ask-again date**. Omit for undated to-dos.
- **`raised::`** — the ISO date the item was first added, auto-stamped once and never changed. This is the field that makes aging computable (`today − raised`).
- **`completed::`** — the ISO date the item was closed, stamped when `status::` flips to `done`. Pairs with `raised::` to make time-to-close computable.

**Priority** is intentionally **not** a field — keep it informal in the description text; order is *derived* (see the Decision below). `owner::` is supported by the parser but optional, and it means something different: see "Not to be confused with".

## Closing an item: say who verified it

**When a closure rests on something that happened outside the repo, name the verifier and what they checked, in the description.** A commit, a green suite or a diff proves code was *written*; it never proves a behaviour was *confirmed*. Much of what actually closes an item happens off-repo — a run on a real device, an endpoint checked by hand, someone's answer — and none of it leaves a trace the vault or an agent can read.

```
- [x] ✅ <description> [status:: done] [raised:: 2026-07-30] [completed:: 2026-07-31]
      → resolved 2026-07-31: **<name> confirmed the flow end-to-end on a real device**
```

An unattributed closure is indistinguishable from an inferred one, and that costs real time: an agent will contest a correctly-closed item as unearned purely because the note records no verifier. Attribution is what stops the next reader re-litigating settled work.

Two rules follow, for everyone working in this vault — human or agent:

- **Never flip an item to `done` from repo evidence alone.** If the real status isn't known, ask the person who owns the work.
- **Never re-open or contest a closure just because the evidence isn't visible in the tree.** Off-repo verification is the norm, not the exception; ask first.

## Not to be confused with

- **[[day-note.template|Task (day-note section)]]** — the day note's `# Tasks` heading is a *rendered view* of open items owned elsewhere, not a place where tasks are born. An item typed only under a day's `# Tasks` with no owning note is the anti-pattern this concept removes.
- **Deadline** — not a separate entity: a **Deadline is an open item that carries a `due::` date**. The day note's `# Deadlines` view is simply the `due::`-bearing subset. Don't model deadlines as a parallel list with its own source of truth.
- **`owner::` vs `assignee::`** — `owner::` is the **note** the item lives in, inferred from the file path and used as the scanner's dedupe key. `assignee::` is the **person or agent** who must act next. An item is *owned by* a note and *assigned to* someone; they are never the same value, and neither defaults from the other.
- **Effort / project** — the *owner* of open items, not an item itself. An effort note holds many open items plus its decision log and prose; the item is the tick-able line, the effort is its home.

## Decision — one source of truth per item

- **Context:** open items tend to get re-typed as prose across day notes, so status drifts, items can't be ticked, and there's no single place to update one.
- **Decision:** one source of truth per item — the owning `[[effort]]`/`[[project]]` note (or a standing ops note for strays) — expressed as a task line with `[status::] [due::] [raised::]` inline fields. Day note and global ledger are generated/queried **views**.
- **Consequences:** every open item must be owned by *some* note; stray/ops items get a standing effort note so nothing is orphaned. Views are rendered two ways (Dataview live in Obsidian + `open-items.py` static fallback), so the schema must stay regex-clean.

## Decision — `assignee::`, and the lanes

- **Context:** the ledger said what was open and when it was due, but never **who would move it**. Once an agent can do real work unattended, "open" is not enough to schedule anything: an item an agent could have finished sits next to one waiting on a colleague, and both wait on you noticing them. A field that is ceremony for solo, unautomated work stops being ceremony the moment something else is supposed to pick items up.
- **Decision:** one inline field, **`assignee::` — who must act next** — and the lanes derived from it. `owner::` is untouched; it is the scanner's dedupe key.

  **Values.** `agent` is a reserved literal. Your own handle comes from `assignees.self` in `aios.config.json`. **Any other name is a real person** — free text, so a wait on a named colleague stops living in prose. Absent means **unrouted**, which is its own lane: absence is *never* read as `agent`, because an agent must never infer it may start work nobody delegated.

  **Routing — `blocked` outranks the lane**, because unblocking is a human act:

  | condition | lane | behaviour |
  |---|---|---|
  | `status:: blocked` (any assignee) | yours | surfaced when `due::` is ripe |
  | `open` + `agent` | agent queue | executed unattended, **once ready** — a future `due::` parks it |
  | `open` + *self* | yours | surfaced when ripe |
  | `open` + another name | silent | never surfaced unless you ask for it |
  | `open` + absent | unrouted | surfaced every session until routed |

- **A wait you intend to chase stays yours.** `assignee::` is *who acts next in your world*, not who owes the answer. Blocked on a colleague and chasing it → your own handle plus `[status:: blocked]`, with their name in the description. Their name in `assignee::` means genuinely handed over — not your problem, and silent. The distinction is **delegation, not who is typing**.
- **`due::` is the ask-again date, for every lane.** No new field: "if nothing has changed by this date, raise it again" is exactly what the live items already encode. Two predicates fall out of it, deliberately different: an item is **ripe** — a disposition is owed from the human — when it is overdue, due today, or unrouted, so an *undated* item is never ripe and the session digest stays short. An agent item is **ready** — the queue may pick it up — when it has no `due::` or the date has arrived, so an *undated* item is ready immediately. Without the second rule the queue executes a re-check deliberately deferred to next month on the day it is written.

  A third case: an **unreadable** `due::` such as `[due:: 2026-10-32]` — a plausible typo — parses as "no date", which is exactly what makes an agent item ready *now*, so the typo walks straight around the rule that parks it. The predicates split on it in opposite directions: **ripe** (show the human, so it gets fixed) and **not ready** (a slip of the keyboard must never authorise unattended work). Because that combination belongs to no single lane, it is also reported as a `⚠️` line across all of them.
- **Deferring writes back, with a reason.** A surfaced item pushed out gets a new `due::` *and* an appended `→ <date> deferred: <reason>` line, in the same style as `→ resolved <date>:`. The reason is **mandatory** — a silent date-push is how an item rots for six months, and the stack of deferral lines is the only evidence distinguishing a well-judged wait from avoidance.
- **Order is derived, never declared.** Blocked-and-ripe → overdue → due soonest → oldest `raised::`. Priority stays out: `assignee::` had a new reason to exist, priority does not.
- **Surfacing.** A `SessionStart` hook runs `open-items.py --lane` and injects the **ripe** digest only — a prompt that fires on every item every session becomes wallpaper, and then nobody answers it. The project's instruction file carries the policy the hook cannot: what a disposition is, and that a **planning-intent opener** ("what should we do today") expands to the *whole* lane in derived order.
- **Agent closure authority.** An agent **may** close what it executed itself, naming itself as verifier — that is attestation, not the forbidden inference from repo evidence. It **may not** close anything needing off-repo proof; that stays `open` and is reassigned to a human with what was done. No new `status::` value is needed.
- **Alternatives:** redefining `owner::` as the person and renaming the note-owner (rejected — rewrites both scripts for a naming preference). A strict `agent|me|other` enum (rejected — throws away *who* you are waiting on, which then returns as prose). A `waiting-on::` field (rejected — a fourth field, and two fields naming people is the confusion `owner`/`assignee` already risks). A `priority::` field (rejected — no new reason, unlike `assignee::`). An `ask-again::` field separate from `due::` (rejected — `due::` already serves). A fourth `status:: review` for agent-finished work (rejected — ripples into every view and query for granularity nobody asked for). An instruction-file rule with no hook (rejected — advisory, and you never learn which sessions skipped it).
- **Consequences:** a fourth lane (unrouted) appears in every view and nags until cleared — deliberate, that is the triage signal. `owner::` and `assignee::` now sit adjacent in the ledger and both sound like ownership; the "Not to be confused with" entry above is the only thing keeping them apart.

**Sources:** `aiOS/templates/day-note.template.md`, `aiOS/runbooks/day-note.runbook.md`, `aiOS/tools/ideaVerse/open-items.py`, `aiOS/aios.config.json`.
