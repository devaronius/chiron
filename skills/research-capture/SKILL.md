---
name: research-capture
description: Validate and place a new note before it enters the ideaVerse — frontmatter, resolvable links, unique basename, and the right folder in the vault taxonomy. Use when creating any new vault note, or when unsure where content belongs.
---

# Research Capture

> **Paths** are relative to the **vault root** — the directory containing `aiOS/`, `ideaVerse/` and `wiki/` (commonly `docs/`). `<vault>` below stands for it. The scripts resolve their own locations, so a command works from any working directory.

Get a new note into the ideaVerse correctly the first time: valid frontmatter, links that resolve, a unique basename, and the right folder.

## The script

Three subcommands (note: these are **subcommands**, not flags):

```bash
python3 <vault>/aiOS/scripts/research-capture.py check   <path-to-note.md>
python3 <vault>/aiOS/scripts/research-capture.py suggest "<content to place>"
python3 <vault>/aiOS/scripts/research-capture.py exists  "<term>"
```

### 1. `exists` — before you write anything

```bash
python3 <vault>/aiOS/scripts/research-capture.py exists "guest driver"
```

Matches basename, first heading and `aliases:` across the vault. The vault's rule is one concept per note with a unique basename — wikilinks resolve *by basename*, so a duplicate silently breaks link resolution. If something already covers the term, **extend that note** instead.

### 2. `suggest` — where does it belong?

```bash
python3 <vault>/aiOS/scripts/research-capture.py suggest "GetTripPalletDetailMobileViewModel gained a required tripType field"
```

Scores the real vault taxonomy and prints the ranked folders:

| Folder | Holds |
|---|---|
| `atlas/concepts/` | domain terms, enums, states, taxonomies — the ubiquitous language |
| `atlas/documents/` | guides, architecture, conventions, onboarding |
| `atlas/apis/` | raw swagger/OpenAPI clippings (different frontmatter: `title`/`source`/`created`) |
| `atlas/personas/` | driver/planner personas |
| `efforts/projects/` | client-facing projects with deadlines |
| `efforts/works/` | epics and works-in-progress |
| `calendar/meetings/`, `research/`, `releases/`, `sprints/`, `days/` | dated records |

Treat the score as a hint. If content spans two folders, that usually means it should be **two single-purpose notes** — `wiki-sync` mines by heading, so a mixed note compiles badly.

### 3. `check` — is the note ready?

```bash
python3 <vault>/aiOS/scripts/research-capture.py check ideaVerse/atlas/concepts/foo.md
```

Verifies:
- **Frontmatter for the note's flavour** — standard notes need `up`/`related`/`created`; `atlas/apis/` clippings need `title`/`source`/`created`
- **Wikilinks resolve** anywhere in the vault (so the briefing note and compiled `wiki/` notes count as valid targets)
- **Basename is unique** against every other vault note
- **Body has substance** (≥50 chars)

## Note structure

Start from `<vault>/aiOS/templates/concept.template.md` (or `api-note.template.md` for a clipping):

```yaml
---
up: ["[[parent-note]]"]
tags: ["tag1", "tag2"]
related: ["[[related-1]]", "[[related-2]]"]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["url / note / commit ref"]
aliases: ["Alias 1"]
---

# Title

**Bold one-line definition.**

## Sections…

## Not to be confused with

- **Term A** vs **Term B** — disambiguation.

> [!open] Open questions
- Question 1?
```

Two conventions worth stating because they are easy to get wrong:

- **`sources:` is mandatory in spirit** — every figure, decision and deadline traces to a source. `note-review` flags a note that asserts versions, tickets, commits or dates while `sources:` is empty.
- **A source is a pointer, not a sentence.** One entry = one locator (a URL, `commit <sha> — <subject>`, `[[note]]`, a work-item id, a Teams chat id + date, a command). Keep just enough label to know which thing it is. Do **not** narrate *how* you obtained it, *when you re-checked it*, *what it proved*, or *what was wrong before* — that belongs in the note body, not in `sources:`. A reader scans this list to go look something up; prose makes it unscannable and quietly turns the frontmatter into a changelog.

  ```yaml
  # good
  sources:
    - "commit 0c306c28 — feat(45428): autocomplete carrier ui added"
    - "[[atlas_taxonomy]]"
  # bad — narration, not a locator
  sources:
    - "commit 0c306c28 (16:12) — feat(45428) (87 files: 17 code + the atlas push); confirmed 2026-07-30 via git log after the local branch was found to be behind"
  ```
- **A "Not to be confused with" section earns its place** whenever a name collides. The vault has three different things called some variant of *trip type*; that section is what stops a later reader conflating them.

## After capture

1. Wire `up:`/`related:` so the note isn't an orphan (`vault-health` will flag it if it is).
2. Run the **`wiki-sync`** skill to compile it into `wiki/`.
3. If the note resolves an open item, flip that item in its **owning** note and re-run `open-items.py`.

## When to use

- Creating any new vault note
- Unsure which folder content belongs in
- Before writing a concept, to avoid duplicating an existing one
