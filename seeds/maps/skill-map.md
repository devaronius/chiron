---
up: ["[[{{BRIEFING_NOTE}}]]"]
tags: ["map", "skills"]
related: ["[[vault-map]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["Skill Map", "intent to skill lookup"]
---

# Skill Map — intent → skill lookup

This is your catalog of every skill you can use on the {{PROJECT_NAME}} project.

**Read this before improvising on any non-trivial request.** Find the row whose intent matches, load that skill, follow it. Each skill's own `SKILL.md` is authoritative on *how*; this map is only for *which*.

Skills live in `.claude/skills/<name>/SKILL.md`. Commands live in `.claude/commands/<name>.md` and are invoked as `/<name>`.

## How to use this map

1. **Match on intent, not on keyword.** The Intent column is phrased as the thing being attempted.
2. **Apply the precedence rules** below when two rows both look right.
3. **Check the Invoke column.** `model` = you may load it yourself. `user only` = it carries `disable-model-invocation: true`; you *cannot* load it, the user must type `/<name>`. Never claim to have run one of those.
4. **If nothing matches, say so** and proceed without a skill — don't force a near-miss.

### Precedence rules

- **A project skill beats a general-knowledge skill.** For work inside this repo the project's own conventions win; general framework skills are for greenfield or how-does-this-work questions.
- **Vault reads before vault writes.** Diagnose with `vault-health` / `contradiction-check` before creating notes with `research-capture` or `domain-modeling`.
- **`wiki-sync` owns `wiki/`.** No other skill compiles or edits the wiki. If a vault skill reports wiki drift, hand off to `wiki-sync`.
- **Never hand-edit generated files.** `open-items.md` comes from `open-items.py`; `wiki/` comes from `wiki-sync.py`; `vault-report.md` sections 1–5 come from `vault-report.py`.

## Project skills

<!-- Add this project's own skills below as you create them under `.claude/skills/`. One row each,
     phrased as an intent. Delete this comment once you have real entries. -->

| Intent | Skill | Invoke |
|---|---|---|
| | | |

## IdeaVerse — diagnose

Run these *before* writing notes. They answer different questions and do not overlap:

| Intent | Skill | Answers | Script |
|---|---|---|---|
| "Is the vault well-formed?" broken links, orphans, empty notes, duplicate basenames, frontmatter | **vault-health** | *structure* | `vault-lint.py` |
| "Where does the vault disagree with itself or the code?" open-item status, deadline dates, stale frontmatter, API fields absent from the spec | **contradiction-check** | *inconsistency* | `contradiction-check.py` |
| "Is *this one note* good?" per-note frontmatter, links, structure, source traceability | **note-review** | *one note* | `note-review.py` |
| "Is the wiki stale?" drift between raw notes and `wiki/` | **wiki-sync** | *compile state* | `wiki-sync.py` |

**Disambiguation:** `vault-health` is the whole vault, `note-review` is one file — use `note-review` when another tool has already pointed at a specific note.

## IdeaVerse — write

| Intent | Skill | Invoke |
|---|---|---|
| Create a new vault note: validate it, find its folder, avoid duplicating a concept | **research-capture** | model |
| Pin down domain terminology / ubiquitous language, or record an architectural decision | **domain-modeling** | model |
| Compile raw notes into `wiki/`, or reconcile wiki drift | **wiki-sync** | model |
| Stand up an ideaVerse in a repo that has none, or upgrade one to the current framework | **bootstrap-ideaverse** | model |

**Disambiguation:** `research-capture` is mechanical (does this note pass? where does it go?). `domain-modeling` is conceptual (what *is* this thing, and what should it be called?). A new concept usually wants `domain-modeling` first, then `research-capture` to place the result.

## IdeaVerse — maintain (agent, not a skill)

| Intent | Agent | Invoke |
|---|---|---|
| Run the whole diagnose→fix loop; reconcile wiki drift; repair links/frontmatter; propose editorial cleanups | **librarian** | model (delegate) |

The librarian is a **subagent**, not a skill — delegate to it rather than loading it. Its behaviour spec is the vendor-neutral runbook [`/aiOS/agents/librarian.md`](/aiOS/agents/librarian.md); `.claude/agents/librarian.md` is a thin adapter over the same runbook.

**Boundary:** the librarian **never authors knowledge** — it only reshapes what already exists. A new note is still `research-capture` / `domain-modeling` in the main session. It applies deterministic fixes only; merges, splits, renames, deletions and effort retirements are written as proposals into `vault-report.md` for a human to approve.

## Thinking / process

| Intent | Skill | Invoke |
|---|---|---|
| Stress-test a plan before building; any "grill" phrasing | **grilling** | model |

---

## Vault scripts (what each skill actually runs)

| Script | Owner skill | Notes |
|---|---|---|
| `vault_lib.py` | *(shared library)* | Not a CLI. Common frontmatter parsing, wikilink resolution across the whole vault, open-item parsing, git helpers, spec extraction, and the `aios.config.json` loader. Import it rather than re-implementing. |
| `vault-lint.py` | vault-health | |
| `contradiction-check.py` | contradiction-check | |
| `note-review.py` | note-review | Takes a single path. |
| `research-capture.py` | research-capture | **Subcommands**, not flags: `check <path>` / `suggest "<text>"` / `exists "<term>"`. |
| `wiki-sync.py` | wiki-sync | Sole writer of `wiki/`. `--update` is all-or-nothing; see the skill. |
| `open-items.py` | *(day-note runbook)* | Regenerates `open-items.md`. Run after changing any `[status::]`. Never edit the ledger by hand. |
| `vault-report.py` | *(librarian agent)* | **Aggregator, not another check.** Rolls the tools above into `vault-report.md` and adds the aiOS invariants (skill-map completeness + its Invoke column, dead absolute paths in `aiOS/`). Section 6 is left for the agent's judgment; every run rewrites the file. Optional tools that aren't installed cost their section, not the report. |

Project-specific *behaviour* comes from `aiOS/aios.config.json`, never from editing a script — an edited script forks permanently from upstream bug fixes. Framework **prose** (runbooks, templates, these maps) is a different case: edit it freely. It becomes CONFLICT and is never overwritten; the only cost is upstream updates to that file.

Two facts about wikilink resolution that repeatedly cause wrong conclusions:

- A `[[target]]` may resolve **outside `ideaVerse/`** — the briefing sits at the vault root, a compiled note lives in `wiki/`, `[[vault-map]]` is this file's neighbour. Resolve against the whole vault.
- **Frontmatter contracts differ by note flavour.** Standard notes carry `up`/`related`/`created`; `atlas/apis/` clippings carry `title`/`source`/`created`.

---

> **Maintenance.** Hand-maintained: when a skill, command or agent is added, removed or renamed under `.claude/skills/`, `.claude/commands/`, `.claude/agents/` or `/aiOS/agents/`, update this file — including the Invoke column, which must match the skill's `disable-model-invocation` frontmatter. The per-skill `SKILL.md` description is the source of truth for behaviour; this map only routes.
>
> Both halves of that contract are **verified automatically** — `vault-report.py` reports a missing row or a mismatched Invoke column as `[MAP]` in section 5 of `vault-report.md`. To check by hand:
> ```bash
> python3 {{VAULT_PREFIX}}aiOS/scripts/vault-report.py --stdout | sed -n '/## 5\./,/## 6\./p'
> ```
