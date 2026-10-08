---
name: ideaverse-vault-health
description: Lint the ideaVerse for structural health — broken links, orphans, empty notes, duplicate basenames, frontmatter gaps, wiki drift. Use after editing vault notes, before adding notes, or on any 'health check' / 'lint the vault' trigger.
---

# IdeaVerse Health Check & Lint

> **Paths.** `aiOS/` sits at the **repo root**, so a command below runs from there. The notes sit in the **vault** — that same root, or the directory named by `vaultDir` in `aiOS/aios.config.json` (`docs/` by default); a path like `ideaVerse/…` is relative to it. The scripts resolve their own locations, so any working directory works.

Structural lint over `ideaVerse/`, then an analytical pass over the results. The script finds *structure* problems; the grilling layer judges whether the vault is actually useful.

## The script

```bash
python3 aiOS/tools/ideaVerse/vault-lint.py              # full report
python3 aiOS/tools/ideaVerse/vault-lint.py --quiet      # summary line only
python3 aiOS/tools/ideaVerse/vault-lint.py --fix        # auto-fix missing 'created' fields
python3 aiOS/tools/ideaVerse/vault-lint.py --categories # add the per-folder count table
```

### What it checks

| Tag | Severity | Meaning |
|---|---|---|
| `[FATAL]` | Blocker | Missing required frontmatter **for that note's flavour** — standard notes need `up`/`related`/`created`; `atlas/apis/` clippings need `title`/`source`/`created` |
| `[BROKEN]` | High | `[[target]]` resolves to no note **anywhere under the whole vault** |
| `[ORPHAN]` | Medium | Note referenced by no other note (root/entry notes in `ROOT_NOTES` are exempt) |
| `[EMPTY]` | Medium | Body under 50 chars |
| `[DUPE]` | High | Two notes share a basename (wikilinks resolve *by basename*, so a collision breaks resolution). **Exempt:** one date-named note per `calendar/` subfolder — a day note and a briefing for the same date is by design, and the vault links those path-style (`[[briefings/2026-07-23]]`) |
| `[STALE]` | High | Wiki drift; delegates to `wiki-sync.py` |
| `[INFO]` | Low | No `sources:` cited |

### Two things this linter gets right — don't "fix" them back

**Links resolve across the whole vault, not just `ideaVerse/`.** the briefing note at the vault root resolves; a compiled `wiki/` note resolves; `[[vault-map]]` is an aiOS map. Scoping resolution to `ideaVerse/` produced 61 broken-link reports of which only ~14 were real. If you see a wave of `[BROKEN]` for notes you know exist, check the scan root before editing notes.

**Required frontmatter is per flavour.** A raw swagger clipping legitimately has no `up:`/`related:`. Treating all notes alike wrongly failed every clipping in `atlas/apis/`.

## The grilling layer

The script cannot judge these. Do it yourself after reading the report.

### 1. Structural integrity
- `[FATAL]` and `[DUPE]` are hard errors — resolve before anything else.
- For `[BROKEN]`, distinguish *typo* (fix the link) from *genuinely absent note* (create it, or drop the link). The common real case is a **missing sprint note** — every day note and briefing links its sprint as parent, so an unstubbed sprint dangles once per note in range. Stub it at sprint start.
- `[STALE]` → reconcile with the **`ideaverse-wiki-sync`** skill; don't hand-edit `wiki/`.

### 2. Connectivity
- Do `up:`/`related:` form a navigable graph, or are there dead ends that make a note unreachable in practice?
- Is every `[ORPHAN]` deliberate? An orphaned concept note means nothing links to the vocabulary — usually a sign the concept was written and then never used.

### 3. Content quality
- Are `atlas/concepts/` notes *defining* a term, or storing narrative that belongs in `atlas/documents/`?
- Is any note covering several topics? Single-purpose headings are what lets `wiki-sync` mine them.
- Do `efforts/works/` notes still reflect reality, or has the code moved on? **The code is the final authority** — a work note describing a shipped design as "planned" is drift.

### 4. Cross-check against the other vault skills
`vault-lint` sees structure only. Pair it with:
- **`ideaverse-contradiction-check`** — where the vault disagrees with *itself* or the spec
- **`ideaverse-wiki-sync`** — whether `wiki/` matches the raw notes

A clean `vault-lint` says the notes you have are well-formed — not that the notes you need all exist.

## Reporting

1. **Health score** — clean / degraded / critical
   - *Clean:* no FATAL, BROKEN, DUPE or STALE
   - *Degraded:* BROKEN links or EMPTY notes, no hard errors
   - *Critical:* FATAL, DUPE, or significant wiki drift
2. **Action items**, ranked by severity, each with the concrete fix.
3. **Grilling insights** — what the structure reveals that the counts don't.

## When to run

- After editing anything under `ideaVerse/` (alongside `wiki-sync`)
- Before adding notes, to avoid duplicate basenames and broken references
- On "health check", "lint the vault", or `/ideaverse-vault-health`
