---
name: daily-day-note
description: Weekday assembly of today's day note from the day's sources
schedule: "At 3:45 PM, Monday–Friday"
cron: "45 15 * * 1-5"
enabled: true
requires: []
---

Assemble (or augment) today's day note. Resolve the repo root first, as `$REPO`: use `$VAULT_REPO` when the scheduler sets it, otherwise derive it from the working directory with `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"`. If neither works, report that and stop; never guess a path. Then `cd "$REPO"` before any other step.

The goal: build today's day note from the day's sources, following [[day-note.runbook]] exactly.

Steps:

1. Read the runbook (`aiOS/runbooks/day-note.runbook.md`) and the skeleton it fills (`aiOS/templates/day-note.template.md`); follow the runbook's workflow.
2. Resolve "today" with `date +%F`. Target: `ideaVerse/calendar/days/<today>.md`. **If it exists, augment it** — merge new findings in, never overwrite. A note started by hand is authoritative where the two disagree.
3. Gather the day's inputs per the runbook: the existing note, repo activity since the last day note, and this project's own sources (see below).
4. Read repo activity with `git -C "$REPO" log --since="<last-day-note-date> 00:00" --pretty=format:'%h %ad %s' --date=short --no-merges`.
5. If any `[status::]` or `[assignee::]` on an [[open_item]] changed, regenerate the ledger: `python3 aiOS/tools/ideaVerse/open-items.py`.

**Project sources — fill this in.** Chat threads, tickets, meeting notes and anything else the day note draws on live *here*, in this schedule, with the address of each and when to read it. They never go in the runbook: `day-note.runbook.md` is a vendor-neutral framework file and names no sources. A source needing a connector or a logged-in browser is declared in `requires:` above, with a `## Without <capability>` section saying what the run does instead.

Guardrails: don't fabricate — every claim traces to a source, and no source means saying so. Write only inside `ideaVerse/calendar/days/`, plus the ledger when a status changed. Never overwrite hand-written content.

End with a short summary of what the note captured and anything a source could not confirm.
