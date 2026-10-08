---
name: ideaverse-coverage-gap
description: Find what the ideaVerse does not document — repo packages, API classes and features with no note, plus missing day notes, briefings and sprint parents. Use to decide what to write next, or on a 'coverage' / 'what's missing' trigger.
---

# Coverage Gap Analysis

What the vault **doesn't** cover yet. Two independent gap classes, because they fail for different reasons and are fixed by different work.

## The script

```bash
python3 aiOS/tools/ideaVerse/coverage-gap.py             # both classes
python3 aiOS/tools/ideaVerse/coverage-gap.py --code      # code-anchored only
python3 aiOS/tools/ideaVerse/coverage-gap.py --calendar  # calendar only
python3 aiOS/tools/ideaVerse/coverage-gap.py --json      # machine-readable
```

### Class 1 — code-anchored (the vault drifting behind the repo)

Every check here reads the `code` block of `aiOS/aios.config.json` and is **skipped when the key it needs is unset** — a vault over a repo the config does not describe reports nothing rather than nonsense.

| Gap | Meaning | Needs |
|---|---|---|
| `module-note-missing` | a package in `<packageDir>/` has no entity note | `packageDir` |
| `app-note-missing` | an app in `<appDir>/` has no entity note (convention: `<appDir>/shop` → `shop-app`) | `appDir` |
| `note-stale-package` | an entity note matching `packagePattern` whose package **no longer exists** — the reverse drift | `packagePattern` |
| `api-undocumented` | a source file contains `apiClassMarker` but is never named in the vault | `apiClassMarker`, `sourceExt` |
| `feature-undocumented` | a `<packageDir>/*/<featureDir>/<feature>/` dir never named in the vault | `featureDir` |

The code is the final authority over the vault — so code with no note is the drift that matters, and a note describing absent code is a lie the vault is telling itself.

### Class 2 — calendar-completeness (holes in the framework's own cadence)

| Gap | Meaning |
|---|---|
| `day-note-missing` | a working day (Mon–Fri) with no `calendar/days/<date>.md` |
| `sprint-note-missing` | day/briefing notes link a sprint note that doesn't exist — stub it at sprint start |
| `briefing-missing` | a working day with no `calendar/briefings/<date>.md` |

Each is **bounded by the earliest existing note of that kind**, so the script reports holes in the period actually being kept — it will never claim you're missing 2019.

### Explicitly not checked

Whether ideaVerse notes are compiled into the wiki. **`ideaverse-wiki-sync`** owns that; duplicating it would give two tools that can disagree.

## Acting on findings

Fix order is severity, then class:

1. **`high`** — a module or app the vault doesn't describe at all. Write the entity note.
2. **`note-stale-package`** — decide: was the package renamed (update the note) or removed (delete the note)? Leaving it makes the vault misleading.
3. **Calendar holes** — a missing sprint note breaks the parent link from every day note and briefing in its range, so `ideaverse-vault-health` reports those as `[BROKEN]` too. Stubbing the sprint note fixes both reports. A day inside a declared absence (`calendar.absences` in `aios.config.json`) is not a working day and is never reported.
4. **`api-undocumented`** — clip the spec into `atlas/apis/` (see [[api-note.runbook]]) or at minimum name the class in the owning concept note.
5. **`feature-undocumented`** (low) — often fine for small features; write it up when the feature acquires real product logic.

To capture anything you research as a result, use the **`ideaverse-research-capture`** skill so it lands in the right folder with valid frontmatter, then run **`ideaverse-wiki-sync`**.

## When to use

- Deciding what to document next
- After a feature lands, to check the vault kept up
- Before a release or handover, to find undocumented surface area
- Alongside `ideaverse-vault-health` (structure) and `ideaverse-contradiction-check` (self-consistency)

## Reading the output

```
Coverage Analysis — 92 notes scanned
Health: MINOR GAPS
Total gaps: 12

Calendar — briefings: 3
     2026-07-24 — no calendar/briefings/2026-07-24.md for this working day
Calendar — sprint parents: 1
  !! 2026 sprint 2 — 16 day/briefing note(s) link [[2026 sprint 2]] but it does not exist
Code-anchored — API contracts: 5
   ! route_api — route_api matches 'extends BaseApi' but is never named in the vault
Code-anchored — packages: 1
   ! pkg_account — entity note 'pkg_account' names a package absent from packages/
```

Markers: `!!` high · `!` medium · blank low. Read it as: one stale entity note to resolve, five API contracts undocumented, and the current sprint has no note yet even though 16 day/briefing notes parent to it.

> **Fix the source before the compiled note.** A stale entity note in the wiki was compiled *from* raw notes whose module trees still list the package — delete the wiki note alone and the next `ideaverse-wiki-sync` recreates it from those same sources. Correct the raw notes first, then recompile.
