---
name: "ideaverse-wiki-sync"
description: "Detect drift between the ideaVerse raw notes and the compiled wiki, then reconcile the wiki. Use whenever asked to update/refresh/rebuild the wiki, after editing notes under ideaVerse/, or to check whether the wiki is stale."
metadata:
  last_modified: "Mon, 29 Jun 2026 00:00:00 GMT"
---
# Wiki Sync

> **Paths.** `aiOS/` sits at the **repo root**, so a command below runs from there. `ideaVerse/` and `wiki/` sit in the **vault** — that same root, or the directory named by `vaultDir` in `aiOS/aios.config.json` (`docs/` by default).

Keep the compiled concept wiki at `wiki/` in step with its raw sources under `ideaVerse/`. The drift detector is `aiOS/tools/wiki/wiki-sync.py`; **this skill is the reconcile loop around it** — the script finds what changed, you (re)compile the affected notes.

The wiki spec lives in two files, both live. Read them before compiling: the briefing note at the vault root sets the first three rules below, [vault-map.md](../../../aiOS/maps/vault-map.md) § *Wiki compilation* and § *Notes that live outside the vault* the last two. Restated here so this skill stands alone:

- **Never overwrite source content** (`ideaVerse/**`) during compilation — the wiki only summarizes it.
- Notes are **short, single-purpose, and source-traceable** (every note ends with a `**Sources:**` line linking the raw file it was compiled from).
- Every note starts with the [base template](../../../aiOS/templates/base.md) frontmatter (`up` / `related` / `created`).
- Compiled notes live under the four default locations: `wiki/topics`, `wiki/concepts`, `wiki/entities`, `wiki/projects`.
- The catalog `wiki/wiki.catalog.jsonl` (one JSON row per note) is the query index — keep it in lock-step with the notes.

---

## Workflow

1. **Detect drift.** From the repo root:
   ```bash
   python3 aiOS/tools/wiki/wiki-sync.py
   ```
   It prints four buckets and exits `1` if any of NEW/CHANGED/DELETED is non-empty:
   - `＋ NEW` — source with no manifest entry → needs a new wiki note.
   - `～ CHANGED` — content hash differs from baseline → the listed `affects:` notes may be stale.
   - `－ DELETED` — tracked source gone → the listed notes are orphaned.
   - `• UNCOVERED` — source no wiki note cites → never compiled.
   - `✗ NOT RECONCILED` — a CHANGED source whose compiled note has an **older `updated:` than the source**. The note was not re-read. This is the check for the trap below; it fires before you can `--update` past it.

   **Read the whole run.** The `NOT RECONCILED` block prints above the summary, so `| tail -2` hides it — which is how it was run past on the day it was written. The count is now repeated in the summary line for exactly that reason, but the block is where the detail is.
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
   python3 aiOS/tools/wiki/wiki-sync.py --update
   ```
   Then a final `python3 aiOS/tools/wiki/wiki-sync.py` must report "Wiki is in sync".

   > **`--update` is global (all-or-nothing).** It re-snapshots *every* source hash, so it marks **all** current drift as "compiled" — including any NEW/CHANGED source you did **not** reconcile this session. If the drift report includes unrelated, pre-existing drift outside your scope, **do not `--update`**: you'd silently baseline (and thus hide) it. Either reconcile that drift too, or stop without re-snapshotting and tell the user which notes are reconciled vs still-drifting so a later, complete pass can baseline everything at once.

   > **The subtler trap: `--update` after a *partial* reconcile of drift you did own.** The warning above is about drift outside your scope. This one bites inside it, and it is the one that actually shipped a defect (2026-09-30, PR 41733).
   >
   > A CHANGED source lists its `affects:` notes. If you edit only the paragraph you happened to be thinking about, then `--update`, the baseline records the whole source as compiled — and **every other paragraph of that note is now silently blessed as current.** No later run will ever flag it, because drift is measured against the baseline you just moved.
   >
   > This is how a compiled note ended up still recommending an option its source had reversed two revisions earlier. The source was correct; the summary was not; the tool reported "in sync" because it hashes sources, never compiled prose.
   >
   > **So: a CHANGED source means re-read the affected note end to end, not just the part you changed.** Ask specifically *what did this reversal falsify elsewhere in the summary?* — a reversal rarely touches one paragraph. `--update` is the last step of a complete reconcile, never a way to quiet the report.

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
- If a source contradicts another source or the project's own instruction file, **do not silently pick one** — flag it inline in the note (a `>` callout) and add it to the "Cross-source discrepancies" list in `wiki/index.md`. The code is the final authority.

---

## Note template

```markdown
---
up: ["[[parent-hub]]"]
tags: ["<inherited from the source note>"]
related: ["[[other-note]]", "[[another]]"]
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: ["<source-basename-without-ext>"]
aliases: ["<inherited from the source note>"]
---

# <Title>

<One-sentence plain definition.>

- <A few concise, single-purpose bullets.>

**Sources:** [<source>.md](../../ideaVerse/<atlas|efforts>/<path>/<source>.md)
```

Source links are relative from `wiki/<subfolder>/` — i.e. `../../ideaVerse/...`. Wikilinks resolve by basename, so `[[a-note]]` works across subfolders.

**Frontmatter is the full [base template](../../../aiOS/templates/base.md) set**, not just the three required fields — the briefing note asks for it on compiled notes. `tags` and `aliases` are **inherited from the note's source(s)** (union, deduped); `sources` lists the same basenames the catalog row carries, so the two cannot drift; `updated` is the compile date. A topic hub that summarises no single source carries `sources: []` and `tags: ["topic", "hub"]`.

## Catalog row format

One JSON object per line in `wiki/wiki.catalog.jsonl`:

```json
{"id":"<basename>","type":"concept|topic|entity|project","path":"<subfolder>/<basename>.md","title":"<Title>","desc":"<one line>","sources":["<source-basename-without-ext>"],"related":["<id>","<id>"],"aliases":["<alt term>","<alt spelling>"]}
```

The `sources[]` tokens are the raw source filenames without extension (e.g. `app_structure`). The sync script matches them back to files, so they MUST match the real source basename — this is what makes CHANGED report the right `affects:` notes.

The `aliases[]` field carries the alternate names/spellings of the note's subject, copied from the source note's `aliases:` frontmatter (empty `[]` if none). It's what lets a term lookup (e.g. in the `ideaverse-modeling` skill) match "Brokerage" to the note it lives in without opening every file. **Populate it for every note you add or touch; existing rows are backfilled lazily** as their notes are next compiled.

---

## Guardrails

- Touch only `wiki/**` (notes + catalog) and the manifest via `--update`. Never edit files under `ideaVerse/**`.
- Keep notes short and single-purpose — if a note grows long or covers two ideas, split it.
- Don't run `--update` until the wiki actually reflects the sources; the baseline is "this is compiled", not "I saw the change".
