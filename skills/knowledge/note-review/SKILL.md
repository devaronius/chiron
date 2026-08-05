---
name: note-review
description: Review a single vault note for quality — frontmatter, link resolution, structure, and source traceability. Use before compiling to the wiki, after editing a note, or when revisiting an old one.
---

# Note Review

> **Paths** are relative to the **vault root** — the directory containing `aiOS/`, `ideaVerse/` and `wiki/` (commonly `docs/`). `<vault>` below stands for it. The scripts resolve their own locations, so a command works from any working directory.

Quality-check **one** note. (For the whole vault at once, use **`vault-health`**.)

## The script

```bash
python3 <vault>/aiOS/scripts/note-review.py <path-to-note.md>
python3 <vault>/aiOS/scripts/note-review.py --json <path-to-note.md>
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
2. **Wikilink resolution across the whole vault** — the briefing note at the vault root, compiled `wiki/` notes and `<vault>/aiOS/` maps are all valid targets. Path-style links like `[[briefings/2026-07-23]]` resolve on their last segment; template placeholders (`[[YYYY-Www]]`) are ignored.
3. **Structure** — body substance, heading presence, and a single-purpose check that flags `vs`/`versus` headings. Em-dash headings are the house style and are *not* flagged. Raw clippings are exempt from the heading check.
4. **Source traceability** — flags a note asserting **versions, ticket numbers, commit SHAs, ISO dates or obligations** (`must`/`should`/`needs to`) while `sources:` is empty. The vault rule is that every figure, decision and deadline traces to a source. Clippings citing `source:` (singular) satisfy this.

## Addressing findings

- **Missing frontmatter** → add the fields for that note's flavour; `vault-lint --fix` can add `created:` alone.
- **Broken link** → distinguish a typo (fix the link) from a genuinely absent note (create it, or drop the link). An unstubbed sprint note is the common real case, since every day note links its sprint as parent.
- **Too short** → expand or merge into the note that should have owned it.
- **`vs` heading** → split if the topics are genuinely distinct; keep and rephrase if it's one concept with a disambiguation section.
- **Unsourced claims** → add `sources:` entries: URLs, work-item ids, commit refs, Teams links, or the day note it came from. Keep each entry a **pointer, not a sentence** — one locator plus just enough label to identify it (`commit 0c306c28 — feat(45428): autocomplete carrier ui added`, `[[atlas_taxonomy]]`). How you obtained it, when you re-verified it, and what it proved go in the body; `sources:` is a list to look things up in, and prose makes it unscannable. The script can't catch this — it only checks whether `sources:` is empty.

Re-run until `excellent`/`good`, then compile with **`wiki-sync`**.

## When to use

- Before `wiki-sync`, so the compile starts from clean notes
- Right after editing a note
- When revisiting an old note, to catch drift
- On a note that **`vault-health`** flagged, to get the per-note detail
