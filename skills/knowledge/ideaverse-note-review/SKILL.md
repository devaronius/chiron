---
name: ideaverse-note-review
description: Review a single vault note for quality — frontmatter, link resolution, structure, and source traceability. Use before compiling to the wiki, after editing a note, or when revisiting an old one.
---

# Note Review

> **Paths.** `aiOS/` sits at the **repo root**, so a command below runs from there. The notes sit in the **vault** — that same root, or the directory named by `vaultDir` in `aiOS/aios.config.json` (`docs/` by default); a path like `ideaVerse/…` is relative to it. The scripts resolve their own locations, so any working directory works.

Quality-check **one** note. (For the whole vault at once, use **`ideaverse-vault-health`**.)

## The script

```bash
python3 aiOS/tools/ideaVerse/note-review.py <path-to-note.md>
python3 aiOS/tools/ideaVerse/note-review.py --json <path-to-note.md>
```

Exit code is 0 for `excellent`/`good`, 1 otherwise — so it composes in a loop.

## Severity

| Severity | Icon | Weight | Meaning |
|---|---|---|---|
| `fatal` | 🔴 | 10 | Missing required frontmatter — note is malformed |
| `broken` | 🟠 | 8 | Wikilink resolves to nothing in the vault |
| `empty` | 🟡 | 6 | Body under 100 chars |
| `suggestion` | 🔵 | 1 | Structure or traceability improvement |
| `info` | ⚪ | 0 | Minor (e.g. no tags) |

Health: `excellent` (0) · `good` (≤2) · `needs work` (≤6) · `poor` (>6). One broken link alone scores `poor` — that's intentional, a dangling link is a real defect.

## What it checks

1. **Frontmatter, per note flavour** — standard notes need `up`/`related`/`created`; `atlas/apis/` clippings need `title`/`source`/`created`. Judging a clipping by the standard contract wrongly fails every one of them.
2. **Wikilink resolution across the whole vault** — the briefing note at the vault root, compiled `wiki/` notes and `aiOS/` maps are all valid targets. Path-style links like `[[briefings/2026-07-23]]` resolve on their last segment; template placeholders (`[[YYYY-Www]]`) are ignored.
3. **Structure** — body substance, heading presence, and a single-purpose check that flags `vs`/`versus` headings. Em-dash headings are the house style and are *not* flagged. Raw clippings are exempt from the heading check.
4. **Research-note sections** — a note under `calendar/research/` must carry a **Method** and a **Limitations** heading. These are the two sections reliably forgotten, because a research note reads finished without them, and they are exactly what a reader who cannot ask the author anything needs: how each finding was obtained, and what the note cannot support. Stubs are exempt — `Structure` already flags those. The shape is [research.template](/aiOS/templates/research.template.md).
5. **Source traceability** — flags a note asserting **versions, ticket numbers, commit SHAs, ISO dates or obligations** (`must`/`should`/`needs to`) while `sources:` is empty. The vault rule is that every figure, decision and deadline traces to a source. Clippings citing `source:` (singular) satisfy this.

## Addressing findings

- **Missing frontmatter** → add the fields for that note's flavour; `vault-lint --fix` can add `created:` alone.
- **Broken link** → distinguish a typo (fix the link) from a genuinely absent note (create it, or drop the link). An unstubbed sprint note is the common real case, since every day note links its sprint as parent.
- **Too short** → expand or merge into the note that should have owned it.
- **`vs` heading** → split if the topics are genuinely distinct; keep and rephrase if it's one concept with a disambiguation section.
- **Unsourced claims** → add `sources:` entries: URLs, work-item ids, commit refs, chat links, or the day note it came from. Keep each entry a **pointer, not a sentence** — one locator plus just enough label to identify it (`commit 0c306c28 — feat(45428): autocomplete carrier ui added`, `[[atlas_taxonomy]]`). How you obtained it and what it proved go in the body; `sources:` is a list to look things up in, and prose makes it unscannable.

> [!note] Fetch dates belong in the entry — decided 2026-09-30
> This rule previously sent *when you re-verified it* to the body along with everything else. That was written when `sources:` was only ever read inside the vault. **`pdf-builder` now renders `sources:` as a References appendix**, so an entry is what a reader outside the team sees — and **a reference nobody can date is a reference nobody can re-check.**
>
> So: append a fetch or verification date to any entry whose target **decays** — vendor pricing, platform behaviour, a live dashboard. `https://example.com/pricing (fetched 2026-09-30)` is a locator plus a label, not prose. A stable target — a commit, a work item, another note — needs no date and should not carry one. The script can't catch this — it only checks whether `sources:` is empty.

Re-run until `excellent`/`good`, then compile with **`ideaverse-wiki-sync`**.

## When to use

- Before `wiki-sync`, so the compile starts from clean notes
- Right after editing a note
- When revisiting an old note, to catch drift
- On a note that **`ideaverse-vault-health`** flagged, to get the per-note detail
