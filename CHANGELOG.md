# Changelog

All notable changes to the chiron aiOS framework. The framework is versioned as **one
unit** — `VERSION` covers everything under `aiOS/`, `seeds/`, `skills/` and `hooks/`. Semver:

- **major** — layout or contract breaks that need a migration step
- **minor** — new files, skills or templates; backward compatible
- **patch** — fixes to existing files

## [2.0.0] — 2026-10-08

Everything the MobileCarrier vault learned since 1.1.1, brought upstream. The layout moves,
so this is a major: `migrations.json` carries 25 renames and an upgrade applies them before
the three-way diff.

### Changed — the layout

- **`aiOS/` installs at the repo root**, not inside the vault. It operates on the repo, not
  only on the notes: `coverage-gap.py` reads the package tree, schedules drive git, and the
  runbooks are read by agents that never open a note. One fixed point also means every
  script derives both roots from its own location — and the vault's directory becomes a
  config key (`vaultDir`) instead of a guess.
- **`aiOS/scripts/` → `aiOS/tools/<group>/`** — `tools/ideaVerse/` for the vault tools,
  `tools/wiki/` for the compiler. The unmanaged escape hatch moves with it, to
  `aiOS/tools/ideaVerse/local/`.
- **`aiOS/agents/` → `aiOS/runbooks/`**, with `*.runbook.md` names. An agent runbook was
  never agent-specific — `day-note.runbook.md` moves out of `templates/` to join it.
- **The vault skills take an `ideaverse-` prefix** — `wiki-sync` → `ideaverse-wiki-sync`,
  `domain-modeling` → `ideaverse-modeling`, and so on. A repo has skills of its own, and an
  unprefixed `note-review` reads as if it belongs to the project rather than to the vault.
- **The manifest moves with `aiOS/`**, to `<repo>/aiOS/.chiron-install.json`. The installer
  still finds a pre-2.0.0 manifest under the vault, upgrades from it, and deletes the old
  copy so the next run cannot read a stale layout as current.
- `.chiron-hashes.json` re-keys every moved payload path, so a file that was pristine before
  the move is still provably pristine after it. Nothing is reclassified as a conflict by the
  rename alone.

### Added — open-item lanes

- **`assignee::` on an open item — who must act next** — and the lanes derived from it:
  `agent` runs unattended, your own handle (`assignees.self`) is surfaced when ripe, another
  name is silent, and **absent is *unrouted***, never read as `agent`. `status:: blocked`
  outranks the lane, because unblocking is a human act.
- `open-items.py --lane [mine|agent|<name>] [--all] [--json]` — one lane, rendered for a
  human or for a machine. **Ripe ≠ ready**: an undated item is never ripe for the human
  digest but is ready for the agent queue immediately, and an unparseable `due::` is ripe
  *and* not ready, so a typo cannot authorise unattended work.
- **`hooks/open-items-lane.py`** — a new payload class, installed to `.claude/hooks/`. It
  prints the ripe digest at SessionStart and exits 0 whatever happens. chiron does **not**
  write `.claude/settings.json`; `bootstrap-ideaverse` offers the wiring and says plainly
  that the file is inert until a human accepts it.

### Added — tools, runbooks, schedules

- **`coverage-gap.py` + `ideaverse-coverage-gap`** — what the vault does not document at
  all: packages, apps, API classes and feature directories with no note, plus missing day
  notes, briefings and sprint parents. Every code-anchored check is driven by the `code`
  block in `aios.config.json` and **skipped when the key it needs is unset**, so a vault over
  a repo the config does not describe reports nothing rather than nonsense.
- **`verify-claims.py`** — re-measures what a note claims (`<!--verify: …-->` markers) and
  fails when a number has moved. It takes a measurement name, never a command: the tool is
  meant to run unattended over notes that carry pasted clippings, so a marker chooses which
  measurement to call and, for some, a path inside the repo — nothing else. The `tests` and
  `suites` measurements read `code.testCommand` from `aios.config.json` and report
  themselves unavailable when it is unset, rather than guessing a runner.
- **`pdf-builder`** — a note becomes a PDF someone outside the team can read, with one
  command: markdown → HTML → headless Chrome, Obsidian never involved. It knows the vault's
  dialect (frontmatter stripped, `[[wikilinks]]` flattened, callouts boxed, `sources:`
  rendered as a References appendix, mermaid fences drawn) and it paginates deliberately —
  no stranded heading, no table split onto a lone row.

  It is the first skill to **ship its own `tests/`**, which install with it: a consumer can
  verify their copy after an upgrade instead of trusting that a renderer change landed
  cleanly. The suite touches no network, launches no Chrome and writes no PDF. Its
  vault-wide citation test reads `vaultDir` from `aios.config.json` rather than assuming
  `<repo>/docs`, and skips rather than fails on a vault too young to have cited anything.
- **Runbooks**: `api-note`, `daily-briefing`, `sprint-note` join `librarian` and `day-note`.
- **Schedules**: `daily-librarian`, `daily-day-note`, `daily-briefing`. Wiki sync is step 3
  of the librarian's evening sweep rather than a routine of its own — as a separate morning
  job it compiled the wiki hours *before* the day note it was meant to pick up.
- **Templates**: `daily-briefing`, `sprint-note`, `research`. `work.template` gains
  `shipped:`/`stub:`; `concept.template` gains `kind:`; `schedule.template` gains `requires:`
  and the harness-capability vocabulary (`browser-control`, `mcp:<server>`), because a
  schedule is the one file in the vendor-neutral ring allowed to name a harness.

### Added — vault rules the scripts now enforce

- **Kinded folders.** `atlas/documents/` notes must declare `kind: external | process |
  stakeholder-reference | backend-request`, and `atlas/concepts/` notes `kind: domain |
  behaviour`. `vault-lint` reports a missing or unknown kind as `[DOC-KIND]`/`[CONCEPT-KIND]`.
  Without it, `documents/` became a dumping ground and `concepts/` collected dated checks
  alongside the domain vocabulary.
- **Declared absences.** `calendar.absences` in `aios.config.json` removes days nobody worked
  from the cadence checks. Each run prints the ranges and the day counts they removed — a
  checker that silently reports less is worse than one that reports too much.
- **Shipped efforts are distilled, then stubbed.** `efforts.stubAfterWorkdays` (14) decides
  when `vault-lint` reports `[INFO] RETIRE`; `vault-map` carries the five-step distillation
  and the rule that a *forecast* is re-measured rather than promoted.
- **`efforts/referrals/`** — outbound artefacts for a reader outside the team, scaffolded
  with the rest of ACE.

### Fixed

- `research-capture.py exists` compared basenames with exact equality
  (`note["basename"].lower() == term.lower()`). Vault basenames are snake_case, so that
  branch **never fired for a term anybody would actually type** — `exists "person identity"`
  matched only by title and alias, and the literal filename was the sole way to reach it.
  The subcommand advertises *"matches basename, first heading and aliases"*: two working axes
  out of three. Basenames now compare after folding separators, so `person identity`,
  `person_identity` and `Person-Identity` are one term. Title and alias matching are
  unchanged and stay substring — they are prose, and a caller searching `personRefId` should
  still find *"Person identity — what personRefId is"*; that looser reach is what lets the
  basename axis stay exact-after-normalising without costing recall.
- `research-capture.py exists` reported a note **once per matching axis**, so a note hit on
  basename, title and alias printed three times and `Found N match(es)` counted hits rather
  than notes. Results are now one line per note listing every axis that matched.
- **A renamed file that the consumer had edited was overwritten by its own migration.** The
  plan is built before `--apply` performs the renames, so every renamed file read as missing
  and the ADD that followed landed on top of the file the rename had just carried over. The
  plan now reads the incoming path when the new one does not exist yet, so a moved file is
  judged on its real content and an edited one comes out CONFLICT. Shipping 25 renames is
  what made this reachable; it has been latent since renames existed.
- A directory emptied by a rename is removed, instead of standing there suggesting the move
  half-failed.

### Upgrading

`--apply` moves every file and writes nothing you have edited. Four things are yours
afterwards, and the migration note repeats them:

1. Point your harness config at the renamed skills, and wire the SessionStart hook.
2. Set `assignees.self` and `vaultDir` in `aios.config.json`.
3. Move anything in `aiOS/scripts/local/` to `aiOS/tools/ideaVerse/local/` — the installer
   never manages that directory, so it cannot move it for you.
4. Merge the two REVIEW maps: `vault-map` and `skill-map` both gained framework sections.

## [1.1.1] — 2026-09-16

### Changed
- **"Configure, don't edit" no longer reads as "never edit a framework file."** The rule
  overstated its own cost and was stranding project knowledge. Editing a framework file
  **loses nothing** — the installer marks it CONFLICT and never overwrites it. What a
  consumer actually gives up is *future upstream updates to that one file*.

  The distinction that matters is prose vs behaviour, not framework vs project:

  - **Prose** — agent runbooks, templates, the maps — is where a project's own knowledge
    legitimately belongs. Editing it is expected, and the CONFLICT is the point: it is how
    local content survives an upgrade.
  - **Behaviour** — anything under `aiOS/scripts/` — should stay byte-identical, because an
    edited script forks permanently from upstream bug fixes. `aios.config.json` and
    `scripts/local/` remain the right homes for project-specific behaviour.

  Found in a consumer vault: a shipped effort's durable content had no home because its
  natural target was a `managed` agent runbook, and the rule read as a prohibition. The
  knowledge stayed in a note nobody would look in. Reworded in `README.md`, the
  `bootstrap-ideaverse` guardrails, and the three seeds that repeat it
  (`project-brief.md`, `vault-root.CLAUDE.md`, `maps/skill-map.md`).
- `seeds/vault-root.CLAUDE.md` now warns that `vault-report.py` **replaces** its judgment
  section, so it should not be run while unrecorded librarian proposals are standing there.

## [1.1.0] — 2026-08-05

### Added
- `.claude-plugin/marketplace.json` — chiron is now a Claude Code plugin marketplace, so
  anyone can `/plugin marketplace add devaronius/chiron` and install from it. Two plugins:
  **`chiron`** (the `bootstrap-ideaverse` installer skill) and **`chiron-productivity`** (the
  grilling skills, useful with or without a vault). Both entries use `"source": "./"` with
  `"strict": false` and name their own skill directories, so no `plugin.json` lives under
  `skills/`. The vault skills stay out of the marketplace on purpose: the installer writes
  them into each repo as managed files, and a global plugin copy would shadow that with an
  unmanaged second one. Plugin skills are namespaced — `/chiron:bootstrap-ideaverse`.
- `chiron-release.py` pins every marketplace plugin entry to `VERSION` on release, and
  `--check` fails when one has drifted. The entry's `version` gates whether installed plugins
  see an update at all, so a stale one strands users on the version they first installed.
- `skills/productivity/grill-me` and `skills/productivity/grill-with-docs` — thin wrappers
  that start a `grilling` session, the second one capturing what the interview settles as
  ideaVerse notes via `domain-modeling`. Both are user-invoked only
  (`disable-model-invocation: true`).

### Changed
- `skills/` now files skills by category: `skills/knowledge/<name>/` for the vault skills,
  `skills/productivity/<name>/` for `grilling` and its wrappers.
  Purely a payload-side layout change — skills still install flat as
  `.claude/skills/<name>/`, because that is where Claude Code discovers them. Nothing moves
  in a consumer repo and no migration is needed.
- `chiron-install.py` finds a skill by the presence of its `SKILL.md` at any depth under
  `skills/`, and flattens the category away on install; `chiron-release.py` reuses that same
  walk. `--map` SRC now includes the category — `--map
  skills/knowledge/wiki-sync=.claude/skills/cca-wiki-sync`.
- `.chiron-hashes.json` history rekeyed to the new payload paths, so a vault installed
  before this release still adopts and upgrades as pristine.

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
