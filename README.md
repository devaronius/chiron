# chiron

> Achilles, Jason, and Asclepius walked in with nothing. They walked out with skills. So will your agents.

A library of agent skills, distributed as Claude Code plugins.

The one it's named for installs a portable **vault** into any repo — Obsidian-style
knowledge notes, the tooling that keeps them honest, and the skills that use it — and
**upgrades it in place** without clobbering what you've written. The rest stand on their own
and need no vault at all.

## Install for Claude

Add the marketplace once, then install whichever plugins you want:

```
/plugin marketplace add devaronius/chiron
/plugin install chiron@chiron                  # the vault installer
/plugin install chiron-productivity@chiron     # grilling — useful with or without a vault
```

Or from a shell, without an interactive step:

```bash
claude plugin marketplace add devaronius/chiron
claude plugin install chiron@chiron
```

| Plugin | Gives you | Needs a vault? |
|---|---|---|
| `chiron` | `/chiron:bootstrap-vault` — installs, adopts, upgrades or verifies a vault in any repo | no, it creates one |
| `chiron-productivity` | `/chiron-productivity:grill-me` and `/chiron-productivity:grill-with-docs` | no |

Plugin skills are **namespaced by plugin name**, which is why they read
`/chiron:bootstrap-vault` rather than `/bootstrap-vault`. The vault skills
(`vault-wiki-sync`, `vault-modeling`, `vault-research-capture`, …) are deliberately *not* in a plugin:
the installer writes them into each repo as managed files so they upgrade in place under the
three-way diff below, and a global plugin copy would shadow that with a second, unmanaged one.

<details>
<summary>Without plugins</summary>

The installer skill works standalone — it fetches its own payload, so a plain copy is enough:

```bash
git clone https://github.com/devaronius/chiron ~/.chiron
mkdir -p ~/.claude/skills
cp -r ~/.chiron/skills/knowledge/bootstrap-vault ~/.claude/skills/
```

Skills are discovered when a session starts, so open a fresh one — then
`/bootstrap-vault` (no namespace, this way) is available in every repo. Note that
`~/.chiron` **stays**: the skill reads the framework from that checkout and refreshes it with
`git -C ~/.chiron pull --ff-only` on every run, so there is exactly one copy and it cannot
drift from what your repos have installed. Delete it and the skill has nothing to install.

Either way the skill belongs at user level, never committed into a target repo — a per-repo
copy is precisely how the previous version of it drifted from its own payload.

</details>

## Using it in a Claude session

Open Claude Code in the repo that should have a vault and ask for it in plain language:

> set up a vault here

Nothing to memorise, and nothing to tell it about the current state: the skill runs
`chiron-install.py --plan` before it writes anything and detects which of four situations it
is in, rather than guessing from a directory listing.

| You ask | It finds | What happens |
|---|---|---|
| "set up a vault here" | no vault | interviews you, shows a plan, applies it |
| "set up a vault here" | a vault, but no chiron manifest | *adopts* it: classifies every file by hash, applies the safe part, reports the rest |
| "upgrade the vault" | a manifest older than chiron | migrations, then the three-way diff below |
| "has the vault drifted?" | a current manifest | reports drift and writes nothing |

You always see the plan — ADD / UPDATE / CONFLICT / REVIEW / RETIRE / KEEP per file — before
anything is written, and `--apply` never touches a CONFLICT or a REVIEW. Those are the two
buckets that need you: ask the agent to merge them and it does it semantically, file by file.

Once the vault exists, the install has wired the repo so later sessions find it on their own:
the vault's `CLAUDE.md` points at `aiOS/maps/`, and the skill-map routes an intent to a skill,
so you keep asking for outcomes rather than naming tools.

| Ask for | Skill |
|---|---|
| "is the vault healthy?" | `vault-health` |
| "what isn't documented at all?" | `vault-coverage-gap` |
| "capture this as a note" | `vault-research-capture` |
| "what do we actually mean by *shipment*?" | `vault-modeling` |
| "is this note any good?" | `vault-note-review` |
| "does the vault contradict the code?" | `vault-contradiction-check` |
| "the wiki is stale" | `vault-wiki-sync` |
| "turn this note into a PDF I can send" | `pdf-builder` |
| "QA this change" / "review PR 812" | the `inspector` agent |
| "go find this out while I'm away" | the `researcher` agent |
| "grill me on this plan" | `grilling` |
| "grill me, and write down what we settle" | `grill-with-docs` — type it, see below |

Two wrappers are yours to invoke by name rather than the model's to pick: **`grill-me`** for a
plain grilling session, **`grill-with-docs`** to also capture what the interview settles as
vault notes. From the plugin they are `/chiron-productivity:grill-me`; installed into a
repo by the vault installer, plain `/grill-me`. For the whole diagnose-and-fix sweep, delegate
to the **librarian** subagent instead — it reshapes what exists and never authors knowledge.

Prefer to drive it yourself, no agent involved?

```bash
python3 ~/.chiron/tools/chiron-install.py --target . --plan
python3 ~/.chiron/tools/chiron-install.py --target . --apply --project-name "Acme"
```

## What gets installed

```
<repo>/
├── aiOS/                        # the operating layer — repo root, beside the vault
│   ├── aios.config.json         # ← all project-specific behaviour lives here
│   ├── maps/                    # vault-map (taxonomy) · skill-map (intent → skill)
│   ├── runbooks/                # vendor-neutral agent runbooks (librarian, day note, …)
│   ├── schedules/               # scheduled routines, one per file
│   ├── templates/
│   └── tools/                   # vault/ · wiki/ · inspector/ — vault/local/ is yours, unmanaged
├── docs/                        # or the repo root, your choice
│   ├── <briefing>.md            # who this project is, how an agent should work here
│   ├── CLAUDE.md
│   ├── vault/                   # ACE: atlas/ · calendar/ · efforts/ · +/
│   └── wiki/                    # compiled, queryable summary of the vault — generated
├── .claude/skills/              # the framework meta-skills, each with its tests
├── .claude/hooks/               # session digest + the two agent scope hooks (you wire them)
└── .claude/agents/              # thin harness adapters: librarian · researcher · inspector
```

**Why `aiOS/` is not in the vault.** It operates on the repo, not only on the notes:
`coverage-gap.py` reads the package tree, the schedules drive git, and the runbooks are read
by agents that never open a note. Keeping it at the root also means one fixed point — every
script derives both the repo root and the vault from its own location, and the vault's
directory is a config key rather than a guess.

**ACE** — Atlas is the mind's landscape (concepts, APIs, documents, personas), Calendar its
rhythm (days, meetings, sprints, releases), Efforts its output (projects, works). The `wiki/`
is a compiled layer: short, single-purpose, source-traceable notes with a
`wiki.catalog.jsonl` an agent can grep before opening broad context.

### The tools

| Script | Answers |
|---|---|
| `vault-lint.py` | Is the vault well-formed? Broken links, orphans, duplicate basenames, frontmatter |
| `contradiction-check.py` | Where does the vault disagree with itself or the code? |
| `coverage-gap.py` | What does the vault not document at all — packages, API classes, missing day notes? |
| `note-review.py` | Is *this one note* good? |
| `wiki-sync.py` | Is the compiled wiki stale? (lives in `tools/wiki/`) |
| `research-capture.py` | Does this new note pass, and where does it belong? |
| `open-items.py` | Regenerates the ledger, and prints one lane (`--lane`) for a human or a hook |
| `verify-claims.py` | Re-measures what a note claims, and fails when a number has moved |
| `vault-report.py` | Rolls the above into one report for the librarian's sweep |

Each has a matching skill in `.claude/skills/`, so an agent routes to it by intent.

### Tests ship with the tooling

`aiOS/tools/run-tests.sh` discovers every Python suite under `aiOS/tools/**/tests` and
`.claude/**/tests` and runs them; `--coverage` adds line coverage when `coverage.py` is
installed, and says so plainly when it is not. The suites ship **into the consumer repo**
rather than staying upstream, so a vault can verify its own copy after an upgrade instead of
trusting that a change landed cleanly. They touch no network and no tracker.

### Three agents

`librarian` (maintain the vault), `researcher` (answer one scoped question unattended) and
`inspector` (QA a change) each ship as a vendor-neutral runbook in `aiOS/runbooks/` plus a
thin `.claude/agents/` adapter. The last two are bounded by `PreToolUse` scope hooks rather
than by their own good intentions: an allowlist of command heads, writes confined to one
note or a scratchpad, and no route to a tracker except the client the project names in
`agents.*.scripts`. chiron ships no such client — that part is yours.

What it does ship is the inspector's **grader**, `aiOS/tools/inspector/grading.py`. Every
finding sits on a five-level ladder — `critical` · `high` · `medium` · `low` · `note` — and
names a rule from `aiOS/runbooks/inspector/severity-rules.toml`, whose level is a floor.
The grader refuses a `critical` finding with no reproduced evidence, a grade under its
rule's floor, and a recommendation the grades contradict (medium or above means *Waiting for
author*). The inspector runs it on its own report in either mode, and your client calls it
before posting. The rule file is seeded: the floors are your team's call.

## Upgrading without losing your work

Running the skill on an existing vault does a **three-way comparison** per file: what's on
disk, what chiron ships now, and what chiron shipped when you installed. That third fact is
the whole trick — without it, "you customised this" and "upstream moved on" look identical,
so an upgrade must either destroy local edits or never update anything.

| Your file | Upstream | Result |
|---|---|---|
| untouched | changed | **updated** |
| you edited it | changed | **left alone**, reported as a conflict |
| missing | exists | **added** |
| exists | retired | **deleted** only if untouched — otherwise kept |

`.chiron-hashes.json` records every hash chiron has ever shipped, so even a vault created
before chiron existed can be *adopted*: a file matching any shipped hash is provably ours
and safe to overwrite; one matching none is yours and is never touched.

Two file classes, distinguished by which directory they ship from:

- **`aiOS/`, `skills/`, `hooks/`** — *managed*. No project tokens, so they upgrade
  automatically for as long as you don't edit them. Skills ship filed by category
  ([`skills/knowledge/vault-wiki-sync`](skills/knowledge/README.md)) and install flat, as
  `.claude/skills/vault-wiki-sync`.
- **`seeds/`** — *seeded*. Rendered once from your project's facts, then yours forever. When
  upstream moves, you get a diff and a merge, never an overwrite. The maps live here, which
  is why your own routing rules survive every upgrade.

**Configure behaviour; edit prose freely.** Everything project-specific about *how chiron
runs* — the briefing note's name, the wiki skill's name, capture vocabulary, repo-root mode —
is in `aiOS/aios.config.json`. Editing a **script** instead forks it permanently from upstream
bug fixes, so project-specific scripts belong in `aiOS/tools/vault/local/`, which the installer
never manages.

Editing a framework **prose** file — an agent runbook, a template, a map — is a different
matter, and it is fine. Nothing is lost: the file becomes a CONFLICT and is never overwritten.
You give up automatic upstream updates to that one file, and you gain a home for knowledge
that would otherwise be stranded somewhere less findable. That trade is usually worth it.

## Repo layout

```
chiron/
├── VERSION  CHANGELOG.md  migrations.json  .chiron-hashes.json
├── .claude-plugin/marketplace.json # both plugins, defined entirely here
├── aiOS/    seeds/    hooks/      # payload — installed into consumer repos
├── skills/                         # payload too, filed by category, installed flat
│   ├── knowledge/                  # the vault skills, and the installer — has a README
│   └── productivity/               # grilling; no vault required
└── tools/                          # chiron's own machinery — never installed
    ├── chiron-install.py           # install · adopt · upgrade · verify
    ├── chiron-release.py           # version bump + shipped-hash history
    └── selftest.sh                 # 66 assertions across 7 scenarios
```

Both plugin entries use `"source": "./"` with `"strict": false`, so each names the skill
directories it exposes (`./skills/knowledge/bootstrap-vault`, `./skills/productivity`) and
nothing under `skills/` needs its own `plugin.json`. Adding a skill to a published category
means editing one file — or nothing at all, if the category is already listed.

A category documents itself: [`skills/knowledge/README.md`](skills/knowledge/README.md) covers
the seven vault skills, which script each owns, why `bootstrap-vault` is the only one not
installed into a repo, and the checklist for adding another.

The framework is versioned as **one unit**: `VERSION` covers every payload directory —
`aiOS/`, `seeds/`, `skills/` and `hooks/`.

### Contributing / releasing

Commit and PR titles are **`type(ticket): summary`** — the issue number with no `#`, since
GitHub appends the PR number itself on squash merge. Types: `feat` · `fix` · `refactor` ·
`docs` · `build` · `chore` · `test`. No issue? Use an area scope (`docs(readme):`) or drop the
scope; don't invent a number. Rebase onto `main` rather than merging it in, so a PR shows only
its own work. `CLAUDE.md` carries these in full, and `.github/PULL_REQUEST_TEMPLATE.md`
applies automatically.

```bash
bash tools/selftest.sh                       # must be green before anything else
claude plugin validate .                     # marketplace + plugin entries
# write the CHANGELOG section first, then:
python3 tools/chiron-release.py --bump minor
git commit -am "chore: release 1.1.0" && git tag v1.1.0
```

`chiron-release.py` pins every marketplace plugin entry to the new `VERSION` and `--check`
fails if one has drifted. That entry's `version` is what decides whether an installed plugin
ever sees an update, so a stale one silently strands users on whatever they first installed.

`selftest.sh` builds throwaway repos and asserts on real applied trees — including that a
locally edited file is byte-identical after an upgrade, that applying twice writes nothing,
and that a file edited before a *rename* survives being moved. Those three are
non-negotiable: everything else being wrong wastes time, while those being wrong destroys
someone's notes silently.

Renames and retirements go in `migrations.json`, applied in version order before the diff:

```json
[{"version": "1.1.0",
  "renames": [["{vault}/aiOS/old.py", "aiOS/new.py"]],
  "retires": ["{vault}/aiOS/templates/gone.md"],
  "moves": [["{vault}/oldNotes", "{vault}/notes"]],
  "note": "surfaced to the agent for follow-up a file copy can't express"}]
```

A **move** renames a whole directory that may hold the consumer's own files — the notes
folder, a `local/` escape hatch. It is judged by the disk rather than the version: it runs
whenever the old directory exists and the new one holds no file, and when both hold files
it is reported BLOCKED and neither is touched.

## License

Apache-2.0.
