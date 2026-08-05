---
name: "wiki-sync"
description: "Detect drift between the ideaVerse raw notes and the compiled wiki, then reconcile the wiki. Use whenever asked to update/refresh/rebuild the wiki, after editing notes under ideaVerse/, or to check whether the wiki is stale."
metadata:
  last_modified: "Mon, 29 Jun 2026 00:00:00 GMT"
---
# Wiki Sync

> **Paths** are relative to the **vault root** — the directory containing `aiOS/`, `ideaVerse/` and `wiki/` (commonly `docs/`). `<vault>` below stands for it. The scripts resolve their own locations, so a command works from any working directory.

Keep the compiled concept wiki at `wiki/` in step with its raw sources under `ideaVerse/`. The drift detector is `<vault>/aiOS/scripts/wiki-sync.py`; **this skill is the reconcile loop around it** — the script finds what changed, you (re)compile the affected notes.

The wiki spec is defined in [the briefing note at the vault root](../../../the briefing note at the vault root) (the "Wiki" section). Read it before compiling. Its non-negotiable rules:

- **Never overwrite source content** (`ideaVerse/**`) during compilation — the wiki only summarizes it.
- Notes are **short, single-purpose, and source-traceable** (every note ends with a `**Sources:**` line linking the raw file it was compiled from).
- Every note starts with the [base template](../../../<vault>/aiOS/templates/base.md) frontmatter (`up` / `related` / `created`).
- Compiled notes live under the four default locations: `wiki/topics`, `wiki/concepts`, `wiki/entities`, `wiki/projects`.
- The catalog `wiki/wiki.catalog.jsonl` (one JSON row per note) is the query index — keep it in lock-step with the notes.

---

## Workflow

1. **Detect drift.** From the repo root:
   ```bash
   python3 <vault>/aiOS/scripts/wiki-sync.py
   ```
   It prints four buckets and exits `1` if any of NEW/CHANGED/DELETED is non-empty:
   - `＋ NEW` — source with no manifest entry → needs a new wiki note.
   - `～ CHANGED` — content hash differs from baseline → the listed `affects:` notes may be stale.
   - `－ DELETED` — tracked source gone → the listed notes are orphaned.
   - `• UNCOVERED` — source no wiki note cites → never compiled.
   If it says "Wiki is in sync", stop — there is nothing to do.

2. **Confirm scope.** Summarize the buckets to the user. If DELETED notes will be removed, or many NEW notes will be created, confirm before large or destructive changes.

3. **Reconcile each bucket** using the playbook below. Read each changed/new source in full first — never compile from the catalog `desc` alone.

4. **Update the catalog.** For every note you add, edit, or remove, update its row in `wiki/wiki.catalog.jsonl` (schema below). One row per note; no orphan rows.

5. **Validate links.** Ensure every `[[wikilink]]` resolves to a real note basename and every relative `Sources:` path resolves:
   ```bash
   cd docs && grep -rhoE '\[\[[a-zA-Z0-9_-]+' wiki --include='*.md' | sed 's/\[\[//' | sort -u
   ```
   Cross-check against `find wiki -name '*.md' -exec basename {} .md \;`. Fix dangling links.

6. **Re-snapshot the baseline** once the wiki matches the sources:
   ```bash
   python3 <vault>/aiOS/scripts/wiki-sync.py --update
   ```
   Then a final `python3 <vault>/aiOS/scripts/wiki-sync.py` must report "Wiki is in sync".

   > **`--update` is global (all-or-nothing).** It re-snapshots *every* source hash, so it marks **all** current drift as "compiled" — including any NEW/CHANGED source you did **not** reconcile this session. If the drift report includes unrelated, pre-existing drift outside your scope, **do not `--update`**: you'd silently baseline (and thus hide) it. Either reconcile that drift too, or stop without re-snapshotting and tell the user which notes are reconciled vs still-drifting so a later, complete pass can baseline everything at once.

---

## Source-area scope

Two vault areas are explicitly in scope (don't leave them uncovered):

- **`efforts/projects/` → `wiki/projects`** — compile each project to a `project` note (scope, status, deadlines).
- **`calendar/days/`, `calendar/briefings/` and `calendar/sprints/`** — do **not** create per-day or per-period wiki notes; the wiki isn't interested in the calendar entry itself. **Mine** each one for documentation-worthy content — **issues reported, deadlines defined, and chat topics/decisions** — and fold it into the relevant concept / entity / project note, adding the entry's basename (e.g. `2026-06-25` for a day, `2026-W26` for a week) to that note's `sources[]` so it reads as covered. An entry with nothing doc-worthy produces no wiki change (it may stay uncovered). Week notes are treated exactly like day notes here — a week note is a synthesized summary of its days, so when one supersedes the days it was merged from, cite the week basename in `sources[]` and retire the now-deleted day basenames via the DELETED bucket.

## Per-bucket playbook

### NEW / UNCOVERED — compile a note
- Read the source. Decide its **type**: `concept` (an idea/pattern), `topic` (a hub linking several notes), `entity` (a named module/app/person/system), or `project` (an effort/work). One source may yield several short single-purpose notes rather than one long one.
- Write each note into the matching subfolder using the note template below.
- Link it: set `up` to its parent hub, add `related` wikilinks, and add it to the relevant topic hub's body.
- Add a catalog row.

### CHANGED — refresh the affected notes
- The report lists the affected note ids under `affects:`. Re-read the source and update only what changed; keep notes short.
- If the change introduces a new sub-topic, it may warrant a new note (treat as NEW) rather than bloating an existing one.
- Update the catalog `desc` if the summary changed.

### DELETED — retire orphaned notes
- The report lists the orphaned notes. Confirm with the user, then remove those note files and their catalog rows.
- Grep for inbound `[[links]]` to the removed notes and fix or remove them so no dangling links remain.

### Discrepancies
- If a source contradicts another source or `CLAUDE.md`, **do not silently pick one** — flag it inline in the note (a `>` callout) and add it to the "Cross-source discrepancies" list in `wiki/index.md`. The code is the final authority.

---

## Note template

```markdown
---
up: ["[[parent-hub]]"]
related: ["[[other-note]]", "[[another]]"]
created: <YYYY-MM-DD>
---

# <Title>

<One-sentence plain definition.>

- <A few concise, single-purpose bullets.>

**Sources:** [<source>.md](../../ideaVerse/<atlas|efforts>/<path>/<source>.md)
```

Source links are relative from `wiki/<subfolder>/` — i.e. `../../ideaVerse/...`. Wikilinks resolve by basename, so `[[a-note-name]]` works across subfolders.

## Catalog row format

One JSON object per line in `wiki/wiki.catalog.jsonl`:

```json
{"id":"<basename>","type":"concept|topic|entity|project","path":"<subfolder>/<basename>.md","title":"<Title>","desc":"<one line>","sources":["<source-basename-without-ext>"],"related":["<id>","<id>"],"aliases":["<alt term>","<alt spelling>"]}
```

The `sources[]` tokens are the raw source filenames without extension (e.g. `app_structure`). The sync script matches them back to files, so they MUST match the real source basename — this is what makes CHANGED report the right `affects:` notes.

The `aliases[]` field carries the alternate names/spellings of the note's subject, copied from the source note's `aliases:` frontmatter (empty `[]` if none). It's what lets a term lookup (e.g. in the `domain-modeling` skill) match "Brokerage" to the note it lives in without opening every file. **Populate it for every note you add or touch; existing rows are backfilled lazily** as their notes are next compiled.

---

## Guardrails

- Touch only `wiki/**` (notes + catalog) and the manifest via `--update`. Never edit files under `ideaVerse/**`.
- Keep notes short and single-purpose — if a note grows long or covers two ideas, split it.
- Don't run `--update` until the wiki actually reflects the sources; the baseline is "this is compiled", not "I saw the change".
