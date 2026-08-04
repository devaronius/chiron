---
up: ["[[{{BRIEFING_NOTE}}]]"]
tags: ["map", "vault"]
related: ["[[skill-map]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["Vault Map", "how to navigate the vault"]
---

# Vault Map — how to navigate & work in the ideaVerse

Your manual for finding things in this vault and filing new notes in the right place.

- **{{BRIEFING_NOTE}}** — `/{{BRIEFING_NOTE}}.md` — your brief on what {{PROJECT_NAME}} is and how to interact
- **vault-map** — `/aiOS/maps/vault-map.md` — this file
- **skill-map** — `/aiOS/maps/skill-map.md` — every skill you can use on my behalf

Harness-specific entry points (e.g. `CLAUDE.md`) must sit at the repo root and are not vault notes.

## Folder structure

The vault follows the **ACE** framework — Atlas = the mind's landscape, Calendar = the mind's rhythm, Efforts = the mind's output.

- `aiOS/` — the AI Operating System: `maps/` (this map + [skill-map](/aiOS/maps/skill-map.md)), `scripts/` (the analysis tools, sharing `vault_lib.py`), `templates/`, `schedules/` (scheduled routines, one per file), `agents/` (**vendor-neutral agent runbooks** — behaviour specs any LLM can execute, e.g. [librarian](/aiOS/agents/librarian.md); a harness-specific adapter wraps each one and carries only the wiring plus its guardrails).
- `atlas/` — the timeless knowledge landscape:
	- `apis/` — raw Swagger/OpenAPI **clippings**, one per backend service, named `<service>_api.md`. Each pairs with a compiled entity note at `wiki/entities/<service>-api.md`. The clipping is verbatim — the code is the final authority on field shapes.
	- `concepts/` — canonical domain-term / **concept** notes (the project's ubiquitous language), one term per note. Use the [concept template](/aiOS/templates/concept.template.md); maintained via the [domain-modeling](/.claude/skills/domain-modeling/SKILL.md) skill. **A concept note owns behaviour** — how a thing actually works, its gotchas, its open questions.
	- `documents/` — **reference & documentation** notes: services, processes, and externals, **and request records** — a documented ask to another team plus its resolution. This is the home for a durable record that is neither our own build work nor a raw clipping. An endpoint's wire contract stays single-sourced in its `apis/` clipping + `wiki/entities/` note; a request record **points to it, never restates it**.
	- `personas/` — user **personas**.
- `calendar/` — the rhythm: `days/`, `briefings/`, `meetings/`, `research/`, `releases/`, `sprints/`.
- `efforts/` — the output:
	- `projects/` — long-running **projects**; compiled to `wiki/projects`.
	- `works/` — discrete design/build **efforts**, each carrying a `status:` frontmatter field — one of `active · shipped · superseded · reference`. There is deliberately no `blocked`: a stuck effort stays `active` with a `[status:: blocked]` open item inside it (see [[open_item]]). New works notes start from the [work template](/aiOS/templates/work.template.md).
- `+/` — inbox (unfiled capture).

### Which atlas folder does this go in?

`concepts/` and `documents/` are **subject-anchored** — you choose where a subject belongs.

| What you have | Goes in |
|---|---|
| How something *behaves*, its gotchas, a domain term | `atlas/concepts/` |
| A process, an external party, a request record | `atlas/documents/` |
| A raw Swagger/OpenAPI dump | `atlas/apis/<service>_api.md` |
| A kind of user, and what they need | `atlas/personas/` |
| Our own build work, with its journey and reversals | `efforts/works/` |

> **Optional: code-anchored folders.** A vault sitting beside code can add folders whose shape is dictated by the repo rather than chosen — one note per package, or per feature directory, with the note's basename matching the directory's. That 1:1 is what lets tooling check coverage mechanically. Add them here when you introduce them, and record the globs under `code` in `aiOS/aios.config.json`.

The overlap to watch is **two folders describing the same subject through different lenses**. Each must stay in its lane; a note that starts restating another lens belongs in that other note instead. The failure mode is not duplication but divergence — the copy drifts, the vault ends up asserting two different things about one subject, and the copy is usually the one that is wrong.

### Folder hubs

A folder with many notes carries a hub note **named after the folder** — `concepts/concepts.md`, `documents/documents.md` — indexing its children in a table. Child notes point at it with `up: ["[[concepts]]"]`.

> **Never name a hub `README.md`.** Wikilinks resolve *by basename*, so several `README.md`s collapse into one unresolvable name: a wikilink to `README` can't work, nothing can link to them (they all lint as ORPHAN), and `up: ["[[…]]"]` dangles in every child. This is not theoretical — three folders once shipped with `README.md` hubs and the rename alone fixed 14 broken links, 3 orphans, a 3-way duplicate and the vault's only FATAL.

### Why the naming matters

**Note basenames must be unique within the vault, and within the wiki.** They are *not* unique across the two, and deliberately so: `wiki-sync.py` keys sources by basename, so a compiled wiki note mirrors the name of the source it was compiled from. A `[[link]]` to one of those pairs is therefore ambiguous between a source and its own compiled summary, which is tolerated because they are the same subject. `vault-lint.py`'s `[DUPE]` check is vault-scoped for this reason, and `research-capture.py check` compares a candidate against the vault only — pointing it at a `wiki/` file would flag every pair.

Within each of those two trees, uniqueness matters for two reasons:

- **Wikilinks resolve by basename**, regardless of folder. Two notes sharing a name means every `[[link]]` to it lands on whichever the resolver picks.
- **The tooling resolves by basename too.** `wiki-sync.py` keys sources by basename; the coverage checks look notes up as bare basenames. **Rename a note and you may silently open a coverage gap.**

On a collision, the **more general / product-domain** meaning keeps the bare name and the **more specific** note takes the qualified one. A worked example: `onboarding` kept its meaning as the app's first-run wizard, and the human-facing docs became `onboarding_developer` + `onboarding_manager` — before the split, 4 of 7 inbound `[[onboarding]]` links had been silently landing on the wrong note.

Run `python3 {{VAULT_PREFIX}}aiOS/scripts/vault-lint.py` after adding notes — it reports basename duplicates as `[DUPE]`.

## Notes that live outside the vault

Some collections sit beside the ideaVerse rather than inside it. They are not part of the ACE structure, but they still follow the vault's note conventions (templates + frontmatter):

- `wiki/` — the **{{PROJECT_NAME}} concept wiki**: a structured wiki organized by concept (`topics/`, `concepts/`, `entities/`, `projects/`), synthesized from the raw notes in `ideaVerse/`. Entry point: `/wiki/index.md`; machine-readable catalog: `/wiki/wiki.catalog.jsonl`. Every note uses the [base template](/aiOS/templates/base.md) frontmatter (`up`/`related`/`created`).

  > **The wiki is generated, never hand-edited.** It is a compiled summary layer; the `ideaVerse/` notes are the source of truth, and every wiki note traces back to a source via its `Sources:` line. To change wiki content, **do not edit `wiki/` directly** — write the data into the best-fit `ideaVerse/` source (or, if none fits, **create a new `ideaVerse/` note** in the right ACE location), then run the **wiki-sync skill**, which detects drift, (re)compiles the affected notes, updates the catalog, and re-snapshots the baseline. A wiki-file write is only ever the *output* of that compile step.

  Drift detection on its own: `python3 {{VAULT_PREFIX}}aiOS/scripts/wiki-sync.py` reports ideaVerse sources that were added/changed/deleted and need (re)compiling (baseline in `/wiki/.wiki-sync.json`); `--update` re-snapshots after reconciling.

## How to create notes properly

Always use a template. When in doubt, use the [base template](/aiOS/templates/base.md), which carries the REQUIRED YAML fields every note starts with: `up`, `related`, `created`.

Templates in `/aiOS/templates`:

- [base](/aiOS/templates/base.md) — the required-frontmatter starting point for any note.
- [concept.template](/aiOS/templates/concept.template.md) — a canonical domain-term / concept note (`atlas/concepts/`): base frontmatter + `aliases`/`sources`, a bold one-line definition, a "Not to be confused with" disambiguation, an open-questions callout, and an optional Decision block. Maintained via the [domain-modeling](/.claude/skills/domain-modeling/SKILL.md) skill.
- [work.template](/aiOS/templates/work.template.md) — a discrete design/build effort (`efforts/works/`).
- [api-note.template](/aiOS/templates/api-note.template.md) — a raw API clipping (`atlas/apis/`).
- [day-note.template](/aiOS/templates/day-note.template.md) — skeleton for a daily note (`calendar/days/<date>.md`); how to build it lives in [day-note.runbook](/aiOS/templates/day-note.runbook.md).
- [schedule.template](/aiOS/templates/schedule.template.md) — a scheduled routine spec (`/aiOS/schedules/`).

> **Rhythm notes beyond the day note** — a morning briefing, a sprint retrospective — are bespoke per team: their runbooks encode which chat tool, tracker and crash reporter you actually use. Add them here as project templates when you write them, paired with a runbook that says how to fill them.

> This convention applies to vault notes **and** to the external collections listed above (e.g. `wiki/`).
