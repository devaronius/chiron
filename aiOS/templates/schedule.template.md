---
name: <schedule-slug>
description: <one line — what runs, and against what>
schedule: "<human reading, e.g. At 6:00 PM, every weekday>"
cron: "<0 18 * * 1-5>"
enabled: true
requires: []          # harness capabilities this routine needs; [] = any harness
---

# <Schedule name>

One file per scheduled routine, in `aiOS/schedules/`. This file is the **spec** — the
scheduler that actually fires it lives outside the vault, so a change here is a change to
the intent, not to the job. Keep them in step; if they disagree, say so in the file.

## Harness requirements

`aiOS/` is the vendor-neutral ring, and a schedule is the **one thing in it allowed to name a
concrete harness** — a runbook never may. Declare that in `requires:` rather than burying it in
a step, and give each entry a `## Without <capability>` section saying what the run does instead.

Vocabulary, deliberately closed — a new value means a new entry here first:

| Capability | Means |
|---|---|
| `browser-control` | drive a logged-in browser session; no API path exists for the source |
| `mcp:<server>` | a named MCP connector must be installed **and** authorized |

Write the neutral instruction first and the harness note in parentheses, the way
`daily-librarian` does: *"Read the runbook … (Claude Code users: the `librarian` subagent wraps
the same runbook — delegate to it rather than doing this inline.)"*

## Prompt

<The exact prompt handed to the agent. Write it as if the agent has no memory of this
file: name the repo root, the skill or runbook to load, and the tools it may use.
Never write an absolute path: the job can run on any machine, under any username, and the
scheduler may not start it inside the checkout. Resolve the repo root as `$REPO`: use
`$VAULT_REPO` when the scheduler sets it, otherwise `dirname "$(git rev-parse
--path-format=absolute --git-common-dir)"` from the working directory. If neither works,
report that and stop. Then `cd "$REPO"` and give every other path relative to it.>

Machine-specific facts belong in the **scheduler entry**, not in this file: each machine
either sets the job's working directory to its checkout or exports
`VAULT_REPO=<path to the checkout>`.

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
