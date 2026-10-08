---
name: daily-briefing
description: Weekday morning briefing — deadlines, health, decisions, recommended focus
schedule: "At 9:00 AM, Monday–Friday"
cron: "0 9 * * 1-5"
enabled: true
requires: []
---

Produce today's briefing. Resolve the repo root first, as `$REPO`: use `$VAULT_REPO` when the scheduler sets it, otherwise derive it from the working directory with `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"`. If neither works, report that and stop; never guess a path. Then `cd "$REPO"` before any other step.

The goal: a concise, decision-oriented briefing built per [[daily-briefing.runbook]], landed where the day can start from it.

Steps:

1. Read the runbook (`aiOS/runbooks/daily-briefing.runbook.md`) and the skeleton it fills (`aiOS/templates/daily-briefing.template.md`); follow the runbook's section order exactly.
2. Resolve "today" with `date +%F`, and "the last working day" as the previous weekday — on a Monday, the prior Friday.
3. Gather the inputs the runbook lists: today's and the last working day's day notes, live projects, works in progress, the open-items lane (`python3 aiOS/tools/ideaVerse/open-items.py --lane`), repo activity, and this project's own sources as listed in the runbook's **Project sources** section.
4. Write to `ideaVerse/calendar/briefings/<today>.md`. One file per day; never overwrite a day note.
5. If any `[status::]` or `[assignee::]` changed while compiling, regenerate the ledger: `python3 aiOS/tools/ideaVerse/open-items.py`.

Guardrails: don't fabricate — every figure, deadline and decision traces to a source, and no source means saying so; link rather than restate; compute dates against today rather than copying a stale "X days left". Report the open-items lane; never re-route an item on the briefing's own initiative.

End with a short summary of what the briefing flagged.
