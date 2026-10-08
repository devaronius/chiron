# {{PROJECT_NAME}} — vault

Start at [{{BRIEFING_NOTE}}.md]({{BRIEFING_NOTE}}.md) — the agent briefing. It points at the
two maps that route everything else:

- [vault-map](/aiOS/maps/vault-map.md) — where each kind of note lives.
- [skill-map](/aiOS/maps/skill-map.md) — intent → skill lookup.

`aiOS/` sits at the **repo root**, beside this vault rather than inside it.

`wiki/` is **generated** from `ideaVerse/` — never hand-edit it. `open-items.md` and
`vault-report.md` are generated too (and `vault-report.py` **replaces** its judgment
section, so don't run it while unrecorded proposals are standing there). Framework files
under `aiOS/` come from [chiron](https://github.com/devaronius/chiron). Editing one is fine
and loses nothing — it is marked CONFLICT and never overwritten — you just stop receiving
upstream updates to that file. Put project knowledge in the prose (runbooks, templates,
maps); keep *behaviour* in `aiOS/aios.config.json` or `aiOS/tools/ideaVerse/local/` so scripts
stay upgradeable.
