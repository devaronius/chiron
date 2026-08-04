# {{PROJECT_NAME}} — vault

Start at [{{BRIEFING_NOTE}}.md]({{BRIEFING_NOTE}}.md) — the agent briefing. It points at the
two maps that route everything else:

- [aiOS/maps/vault-map.md](aiOS/maps/vault-map.md) — where each kind of note lives.
- [aiOS/maps/skill-map.md](aiOS/maps/skill-map.md) — intent → skill lookup.

`wiki/` is **generated** from `ideaVerse/` — never hand-edit it. `open-items.md` and
`vault-report.md` are generated too. Framework files under `aiOS/` come from
[chiron](https://github.com/devaronius/chiron); configure behaviour in
`aiOS/aios.config.json` rather than editing a script, or the next upgrade will conflict
with your edit.
