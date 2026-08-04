# Changelog

All notable changes to the chiron aiOS framework. The framework is versioned as **one
unit** — `VERSION` covers everything under `aiOS/`, `seeds/` and `skills/`. Semver:

- **major** — layout or contract breaks that need a migration step
- **minor** — new files, skills or templates; backward compatible
- **patch** — fixes to existing files

## [1.0.0] — 2026-08-04

First release. Harvested from the ChainCargo Mobile App vault, where the framework grew,
and genericized so it installs into any repo.

### Added
- `aiOS/scripts/` — nine tools: `vault_lib.py` (shared library), `vault-lint.py`,
  `wiki-sync.py`, `open-items.py`, `note-review.py`, `research-capture.py`,
  `contradiction-check.py`, `vault-report.py`.
- `aiOS/aios.config.json` — all project-specific behaviour (briefing note name, wiki skill
  name, capture keywords, code vocabulary, repo-root mode). Scripts read it and are
  otherwise identical across every vault, which is what makes them upgradeable in place.
- `aiOS/agents/librarian.md` — vendor-neutral vault-maintenance runbook, path-relative and
  name-neutral so it upgrades without touching consumer specifics.
- `aiOS/maps/` — `vault-map.md` (ACE taxonomy, naming rules) and `skill-map.md`
  (intent → skill routing, precedence rules).
- `aiOS/templates/` — `base`, `concept`, `work`, `api-note`, `day-note` (+ runbook), and
  `schedule`.
- `skills/` — `bootstrap-ideaverse` (the installer skill), `domain-modeling`, `grilling`,
  `vault-health`, `note-review`, `research-capture`, `contradiction-check`, `wiki-sync`.
- `seeds/` — rendered once at install, then owned by the consumer: the briefing note, the
  vault `CLAUDE.md`, `aios.config.json`, the Claude librarian adapter, the `open_item` seed
  concept, and a wired wiki baseline.
- `tools/chiron-install.py` — install / adopt / upgrade / verify, with a plan shown before
  anything is written.
- `tools/chiron-release.py` — version bump plus the accumulating shipped-hash history.
- Repo-root vaults are supported (`--at-repo-root`) alongside the default `docs/`.

### Fixed relative to the vault this was harvested from
- `REPO_ROOT` resolved to the vault's *parent* unconditionally, which at a repo-root vault
  pointed outside the repo — so `git log` and the skills scan silently read the wrong
  directory. Now driven by `vaultAtRepoRoot`.
- Wikilink resolution walked the whole vault tree, which at a repo-root vault would pull in
  every `README.md`, `CHANGELOG.md` and vendored dependency; broken links would then
  resolve against unrelated files. Now restricted to explicit scan roots — byte-identical
  behaviour for a `docs/`-style vault.
- `vault-report.py` hard-required `coverage-gap.py` and died entirely when it was absent.
  Optional tools now cost their own section, not the whole report.
- The dead-absolute-path check matched only `/Users/…`, missing every Linux home.

### Not included
- `coverage-gap.py` and its skill — the code-side checks are still hardcoded to a Dart
  monorepo (`modules/`, `apps/`, `lib/feats/`, `extends ManagementApi`). Landing in 1.1.0
  behind the `code` globs in `aios.config.json`.
- Morning-briefing and sprint-note templates — their runbooks encode one team's chat tool,
  tracker and crash reporter. The skeleton without the runbook is a form with no
  instructions; deferred until they can ship as a pair.
- `kanban-sync.py` and its board — retired at the source.

### Hash-history baselines
Two pre-release generations are recorded in `.chiron-hashes.json` so vaults created before
chiron existed can be *adopted* rather than reported as one large conflict:

- `0.9.0` — the payload bundled in the old `bootstrap-ideaverse` skill's `assets/`.
- `0.9.1` — the live ChainCargo vault that 1.0.0 was harvested from.

Neither was ever tagged. They exist only so a file that came from us is recognisable as
ours, and never overwrites work that did not.
