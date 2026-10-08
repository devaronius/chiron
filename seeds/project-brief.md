---
up: []
tags: ["briefing"]
related: ["[[vault-map]]", "[[skill-map]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["{{PROJECT_NAME}}", "agent briefing", "project brief"]
---

# {{PROJECT_NAME}} — agent briefing

Who {{PROJECT_NAME}} is and how to work in its **ideaVerse** (the Obsidian-style vault this
note sits in). Read this first, then follow it to the two maps below. The operating layer
`aiOS/` sits at the repo root, beside the vault; a path starting `/aiOS/` is repo-relative.

## What this is

{{PROJECT_DOMAIN}}

## Orient before acting

- **[vault-map](/aiOS/maps/vault-map.md)** — how the vault is structured and where each kind of note lives. Consult before creating or filing any note.
- **[skill-map](/aiOS/maps/skill-map.md)** — the skills defined for you (intent → skill lookup).

## Operating rules

- **Skills first.** Before any non-trivial request, check the [skill-map](/aiOS/maps/skill-map.md) for a matching skill and use it instead of improvising — this is how the ideaVerse becomes powerful.
- **The wiki is generated, never hand-edited.** `wiki/` is a compiled summary of the vault sources. To change it, edit the best-fit vault source (or create one in the right place per the [vault-map](/aiOS/maps/vault-map.md)), then run the **`{{WIKI_SKILL}}`** skill — never write to `wiki/` by hand. Query `wiki/index.md` + `wiki/wiki.catalog.jsonl` before opening broad context.
- **Code is the final authority.** The vault and wiki summarize the system; when a note disagrees with the code, trust the code and flag the drift.
- **Configure behaviour; edit prose freely.** Framework files under `aiOS/` come from [chiron](https://github.com/devaronius/chiron). Editing one loses nothing — it is marked CONFLICT and never overwritten — you only stop receiving upstream updates to that file. So put project knowledge in the prose (runbooks, templates, maps) where it belongs, and keep *behaviour* in `aiOS/aios.config.json` or `aiOS/tools/ideaVerse/local/` so scripts stay upgradeable.

{{ROLES_SECTION}}

## Wiki compilation

### Default write locations
- Topics hubs: `wiki/topics`
- Concepts: `wiki/concepts`
- Entities: `wiki/entities`
- Projects: `wiki/projects`

### Compilation scope
Compile from the whole vault — for the source-folder taxonomy (which kind of note lives where), defer to the [vault-map](/aiOS/maps/vault-map.md). Two areas need explicit handling:
- **`efforts/projects/` → `wiki/projects`** — compile each project (scope, status, deadlines) to a project note.
- **`calendar/days/`** — do **not** create per-day wiki notes. Instead **mine each day** for documentation-worthy content — issues reported, deadlines defined, decisions — and fold those into the relevant concept / entity / project notes (which then cite the day note as a source). A day with nothing doc-worthy produces no wiki change.

### Non-negotiable rules
- Do not overwrite source content during wiki compilation.
- Use the [base template](/aiOS/templates/base.md) frontmatter on compiled wiki notes.
- Keep compiled notes short, single-purpose, and source-traceable.
