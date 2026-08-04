---
name: <schedule-slug>
description: <one line — what runs, and against what>
schedule: "<human reading, e.g. At 6:00 PM, every weekday>"
cron: "<0 18 * * 1-5>"
enabled: true
---

# <Schedule name>

One file per scheduled routine, in `aiOS/schedules/`. This file is the **spec** — the
scheduler that actually fires it lives outside the vault, so a change here is a change to
the intent, not to the job. Keep them in step; if they disagree, say so in the file.

## Prompt

<The exact prompt handed to the agent. Write it as if the agent has no memory of this
file: name the repo root, the skill or runbook to load, and the tools it may use.>

## Steps

1. <Load the skill or runbook that owns this work — by name **and** path, so a harness
   without skill support can just read the markdown.>
2. <The work itself.>
3. <What to write, and where.>

## Rules

- <Anything the routine must never do unattended — the destructive or all-or-nothing
  operations. An unattended run has no human to catch a wrong call.>
- <What to do when a source is unavailable: report it, never silently skip. A quiet
  omission reads as "nothing was wrong".>

## Retiring a schedule

Set `enabled: false`, add `superseded_by: <other-schedule>`, and leave the file as
history with a note saying when and why:

```markdown
> [!warning] Retired <date> — superseded by `<other-schedule>`.
> <Why, in one or two lines.>
```

Setting `enabled: false` here is **only a spec change** — also disable the job in the
scheduler that actually runs it, or the retired routine keeps firing alongside its
replacement.
