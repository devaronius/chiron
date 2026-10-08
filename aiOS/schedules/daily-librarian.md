---
name: daily-librarian
description: Evening vault maintenance sweep — diagnose, apply tier-1 fixes, reconcile the wiki, regenerate vault-report.md
schedule: "At 6:00 PM, every day"
cron: "0 18 * * *"
enabled: true
requires: []
---

Run the **librarian** maintenance sweep for this vault. Resolve the repo root first, as `$REPO`: use `$VAULT_REPO` when the scheduler sets it, otherwise derive it from the working directory with `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"`. If neither works — the variable is unset and the job did not start inside the checkout — report that and stop; never guess a path. Then `cd "$REPO"` before any other step.

The goal: keep the ideaVerse and the compiled wiki healthy without a human in the loop — repair what is deterministic, and write everything else up as proposals rather than acting on it.

This runs in the **evening, after the day note lands**, so the day's note is compiled the same day instead of waiting for the next morning. Wiki sync is step 3 of this sweep rather than a routine of its own: as a separate morning job it compiled the wiki hours *before* the day note it was meant to pick up.

Steps:

1. Read the runbook `aiOS/runbooks/librarian.runbook.md` and follow it exactly. It is the source of truth for the sweep, the tier-1 fix table, and the proposal format. (Claude Code users: the `librarian` subagent at `.claude/agents/librarian.md` wraps the same runbook — delegate to it rather than doing this inline.)
2. Diagnose with `python3 aiOS/tools/ideaVerse/vault-report.py`, then read the `vault-report.md` it writes.
3. Reconcile any wiki drift per the wiki-sync skill named in [[skill-map]]. Re-snapshot with `python3 aiOS/tools/wiki/wiki-sync.py --update` **only if you reconciled everything** — it is all-or-nothing and will silently baseline drift you skipped.
4. Apply tier-1 fixes only (broken wikilinks, missing frontmatter, missing `sources:`, stale `updated:`, dead aiOS paths, skill-map drift). Re-run `python3 aiOS/tools/ideaVerse/open-items.py` if any `[status::]` changed.
5. Re-run `vault-report.py`, then write your proposals under the `<!-- LIBRARIAN:PROPOSALS -->` marker in section 6.

Guardrails: **never author new knowledge** — a coverage gap is reported, never filled. **Never rename or delete a note unattended**; those are proposals. Write only `ideaVerse/**`, `wiki/**`, `vault-report.md` and `aiOS/{maps,schedules,templates}/` — never `aiOS/tools/`, `aiOS/runbooks/`, `.claude/**`, or any code. The code is the final authority when a note disagrees with it.

End with a short summary of what was found, what was fixed, what is proposed, and anything deliberately left alone.
