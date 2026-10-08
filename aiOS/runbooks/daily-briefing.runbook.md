---
up: []
tags: ["runbook", "daily-briefing"]
related: ["[[daily-briefing.template]]", "[[day-note.runbook]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["Daily Briefing Runbook", "daily-briefing"]
---

# Daily Briefing — Assembly Runbook

How to produce the morning briefing: what needs attention today, drawn from what the vault already knows. This is the **runbook**; the skeleton it fills lives in [[daily-briefing.template]].

> **Audience:** whoever runs the project. Tone: concise, direct, decision-oriented. No filler. Lead with what needs attention.

A briefing is **not** a day note. The day note is the record of a day that happened; the briefing is a read of the day about to start, and it is written *from* the day notes rather than beside them.

## When this runs

Weekday mornings, before work starts — unattended, on a schedule. "Since the last working day" means the previous weekday: on a Monday that is the prior **Friday**, so the weekend gap is covered rather than skipped.

## Inputs (where to look)

Resolve "today" with `date +%F`. Then gather, in order:

1. **Today's day note** — `ideaVerse/calendar/days/<today>.md`. The primary source. If it does not exist yet, say so and work from the rest.
2. **The previous working day's note(s)** — what changed, and what carried over.
3. **Projects** — `ideaVerse/efforts/projects/*.md` for live deadlines and status.
4. **Works in progress** — `ideaVerse/efforts/works/*.md`.
5. **The open-items lane** — `python3 aiOS/tools/ideaVerse/open-items.py --lane` for what is ripe, and `--lane agent` for what ran unattended. Report the lane; never re-route an item on the briefing's own initiative.
6. **Repo activity** — the work itself, which the notes can only partly see:
   ```bash
   git log --since="<last-working-day> 00:00" --pretty=format:'%h %ad %s' --date=short --no-merges
   ```
7. **Wiki drift (optional)** — `python3 aiOS/tools/wiki/wiki-sync.py` flags stale compiled notes. Mention it only when it surfaces something actionable.

### Project sources

Every project has sources no framework can name — a monitoring console, a chat workspace, a tracker, a store dashboard. **List them here, in this file, with how to reach each one and what to pull.** Two rules make them trustworthy:

- **Fetch every run, and never silently skip.** A quiet omission reads as "nothing was wrong". If a source cannot be reached, fall back to the most recent dated snapshot in the vault, say which date it came from, and flag the staleness in the TL;DR.
- **Name the capability, not the vendor, in the schedule.** A source needing a logged-in browser or a connector belongs in the schedule's `requires:` with a `## Without <capability>` fallback (see [[schedule.template]]). This runbook stays harness-neutral.

## Sections

Fill [[daily-briefing.template]] in order. Each section earns its place or says why it is empty:

1. **TL;DR** — the three things that actually matter today, including any failed fetch.
2. **Deadlines & milestones** — computed against today, never copied from yesterday's "X days left".
3. **Health** — whatever the project measures: stability, errors, engagement. One row per snapshot date so a trend is visible.
4. **Decisions & discussions** — what was decided and by whom, in the decider's own wording, linked to its source note.
5. **Open items** — grouped by the discipline that must act, not one flat list.
6. **Work since the last working day** — grouped by theme, not a raw commit dump.
7. **Recommended focus** — ordered, opinionated, each item tied to a deadline, a trend or a blocker named above. Show the reasoning in a clause; surface a tradeoff where one exists.

## Output

Write to `ideaVerse/calendar/briefings/<today>.md` — one file per day, never overwriting a day note. Use the frontmatter from [[daily-briefing.template]], set `created`/`updated` to today, and list every source you used in `sources`.

## Refresh the ledger

If writing the briefing changed any `[status::]` or `[assignee::]` on an [[open_item]] in an owning note, regenerate the ledger:

```bash
python3 aiOS/tools/ideaVerse/open-items.py
```

The owning note stays canonical; `open-items.md` is a generated view and is never hand-edited. Skip this only if the briefing raised or closed nothing.

## Rules

- **Don't fabricate.** Every figure, deadline and decision traces to a source. No source → say so.
- **Link, don't restate.** `[[wikilinks]]` to the projects and notes; the briefing stays short.
- **Compute dates against today.** Never carry a stale countdown forward.
- **A stale figure is reported as stale.** Date it and say the fetch failed, rather than presenting it as this morning's.
- **The briefing reports the lane; the human disposes of it.** Starting work nobody assigned is the failure this rule prevents.
