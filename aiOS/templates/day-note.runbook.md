---
up: []
tags: ["runbook", "day-note"]
related: ["[[day-note.template]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["Day Note Runbook"]
---

# Day Note — Assembly Runbook

How to assemble a **day note** from the day's sources. This is the **runbook**; the output skeleton it fills lives in [[day-note.template]].

> Tone: concise, direct, decision-oriented. **Summarise — don't transcribe.** Lead with what needs action.

## When this runs

End of the working day, or on demand. One note per working day. A note for today may already exist (started by hand during the day) — **augment** it: merge new findings in, never overwrite what's there.

## Inputs (where to look)

Resolve "today" with `date +%F`, then gather from whatever sources this project actually uses:

1. **Today's day note (if any)** — `ideaVerse/calendar/days/<today>.md`. Hand-written content is authoritative; add to it.
2. **The day's discussions** — chat threads, meetings, reviews touching the work. Filter banter; capture gist + decision + who.
3. **Repo activity** — commits since the last day note:
   ```bash
   git -C <repo> log --since="<last-working-day> 00:00" --pretty=format:'%h %ad %s' --date=short --no-merges
   ```
   plus any PRs opened/reviewed today.
4. **Trackers** — tickets/stories/bugs touched today.
5. **Projects** — `ideaVerse/efforts/projects/*.md` for the deadline/status a task or release ties back to.

## Format — the at-a-glance layer & open-item schema

The day note leads with a scannable layer, then the rich prose below it (skim first, drill down).

- **At-a-glance callout.** Right under the summary blockquote, a `> [!tldr] At a glance` callout: a one-line count strip (`✅ shipped · 🔴 waiting · ⏳ active · 📅 deadline`) then 3–4 bullets — what shipped, what's blocked (and on whom), the single **Resume here** next action, and the nearest deadline.
- **Status glyphs** on every Deadline/Task line: ✅ done · 🔴 blocked · ⏳ open.
- **State callouts** for the high-signal states only: `> [!danger]` wraps dated commitments, `> [!warning]` groups blocked / waiting-on-others items at the top of Tasks. Keep the prose body plain.
- **Open-item schema.** Every Deadline/Task is an [[open_item]] carrying Dataview inline fields, regex-parseable by `open-items.py`:

  ```
  - [ ] ⏳ <desc> [status:: open|blocked|done] [due:: <YYYY-MM-DD>?] [raised:: <YYYY-MM-DD>]
  ```

  `status::` — `open`/`blocked`/`done` (a checked box implies `done`); `due::` — only for dated commitments (its presence makes the item a Deadline); `raised::` — the date the item first appeared, **stamped once, never changed** (it drives aging).
- **Ownership.** Recurring/unowned items don't get re-typed each day — they live in a standing effort/project note; reference them. Work tied to an effort/project links its `[[note]]`.

## Output

Write or merge into `ideaVerse/calendar/days/<today>.md`. One file per day; never overwrite a prior day. Set `created`/`updated`, add relevant `[[project]]`s to `related`, and list every source used in `sources`.

Then refresh the cross-note **[open-items ledger](../../open-items.md)**:

```bash
python3 ideaVerse/aiOS/scripts/open-items.py --today <today>
```

It re-scans every [[open_item]] in the vault, recomputes aging from `raised::`, and rewrites `ideaVerse/open-items.md`. `--check` prints without writing and exits non-zero if the ledger is stale — handy in CI.

## Rules

- **Tasks & deadlines under their category** — lift them out of prose into Tasks / Deadlines, each with glyph + [[open_item]] schema.
- **Don't track commit/push/PR as open items** — those are part of *finishing* a task, not separately-tracked work. Track only genuine forward work (deferred phases, pending verification, rollout).
- **Close superseded/resolved items in their owning note** — flip `[status::]` → `done` (glyph → ✅) and append a short `→ resolved <date>: …` in place, then re-run `open-items.py` so the ledger clears the stale entry.
- **Summarise, don't transcribe** — gist + decision + who; no message-by-message replay.
- **Source-traceable** — every figure / decision / deadline traces to a source; `[[wikilinks]]` inline, links in `sources`. No source → say so.
- **Don't fabricate.**
- **Single-purpose headings** — so `wiki-sync` can mine issues, deadlines and decisions into the concept / entity / project notes.
