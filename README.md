# chiron

> Achilles, Jason, and Asclepius walked in with nothing. They walked out with skills. So will your agents.

A portable **ideaVerse** for coding agents: an Obsidian-style knowledge vault, the tooling
that keeps it honest, and the agent skills that use it — installable into any repo and
**upgradeable in place** without clobbering what you've written.

## Install

```bash
git clone https://github.com/devaronius/chiron ~/.chiron
cp -r ~/.chiron/skills/bootstrap-ideaverse ~/.claude/skills/
```

That puts one copy of the installer skill at user level, available in every repo you open.
Then, in any repo:

> set up an ideaVerse here

The skill interviews you, shows a plan, and applies it. To upgrade later, or check whether a
vault has drifted, run it again — it detects which situation it's in.

Prefer to drive it directly?

```bash
python3 ~/.chiron/tools/chiron-install.py --target . --plan
python3 ~/.chiron/tools/chiron-install.py --target . --apply --project-name "Acme"
```

## What gets installed

```
<repo>/
├── docs/                        # or the repo root, your choice
│   ├── <briefing>.md            # who this project is, how an agent should work here
│   ├── CLAUDE.md
│   ├── aiOS/
│   │   ├── aios.config.json     # ← all project-specific behaviour lives here
│   │   ├── agents/librarian.md  # vendor-neutral vault-maintenance runbook
│   │   ├── maps/                # vault-map (taxonomy) · skill-map (intent → skill)
│   │   ├── scripts/             # the analysis tools; scripts/local/ is yours, unmanaged
│   │   ├── schedules/           # scheduled routines, one per file
│   │   └── templates/
│   ├── ideaVerse/               # ACE: atlas/ · calendar/ · efforts/ · +/
│   └── wiki/                    # compiled, queryable summary of ideaVerse — generated
├── .claude/skills/              # the framework meta-skills
└── .claude/agents/librarian.md  # thin harness adapter over the runbook
```

**ACE** — Atlas is the mind's landscape (concepts, APIs, documents, personas), Calendar its
rhythm (days, meetings, sprints, releases), Efforts its output (projects, works). The `wiki/`
is a compiled layer: short, single-purpose, source-traceable notes with a
`wiki.catalog.jsonl` an agent can grep before opening broad context.

### The tools

| Script | Answers |
|---|---|
| `vault-lint.py` | Is the vault well-formed? Broken links, orphans, duplicate basenames, frontmatter |
| `contradiction-check.py` | Where does the vault disagree with itself or the code? |
| `note-review.py` | Is *this one note* good? |
| `wiki-sync.py` | Is the compiled wiki stale? |
| `research-capture.py` | Does this new note pass, and where does it belong? |
| `open-items.py` | Regenerates the open-items ledger from the notes that own each item |
| `vault-report.py` | Rolls the above into one report for the librarian's sweep |

Each has a matching skill in `.claude/skills/`, so an agent routes to it by intent.

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

- **`aiOS/`, `skills/`** — *managed*. No project tokens, so they upgrade automatically for as
  long as you don't edit them.
- **`seeds/`** — *seeded*. Rendered once from your project's facts, then yours forever. When
  upstream moves, you get a diff and a merge, never an overwrite. The maps live here, which
  is why your own routing rules survive every upgrade.

**Configure, don't edit.** Everything project-specific — the briefing note's name, the wiki
skill's name, capture vocabulary, repo-root mode — is in `aiOS/aios.config.json`. Editing a
script instead turns it into a permanent conflict. Project-specific scripts belong in
`aiOS/scripts/local/`, which the installer never manages.

## Repo layout

```
chiron/
├── VERSION  CHANGELOG.md  migrations.json  .chiron-hashes.json
├── aiOS/    seeds/    skills/     # payload — installed into consumer repos
└── tools/                         # chiron's own machinery — never installed
    ├── chiron-install.py          # install · adopt · upgrade · verify
    ├── chiron-release.py          # version bump + shipped-hash history
    └── selftest.sh                # 42 assertions across 5 scenarios
```

The framework is versioned as **one unit**: `VERSION` covers all three payload directories.

### Contributing / releasing

```bash
bash tools/selftest.sh                       # must be green before anything else
# write the CHANGELOG section first, then:
python3 tools/chiron-release.py --bump minor
git commit -am "chore: release 1.1.0" && git tag v1.1.0
```

`selftest.sh` builds throwaway repos and asserts on real applied trees — including that a
locally edited file is byte-identical after an upgrade, and that applying twice writes
nothing. Those two are non-negotiable: everything else being wrong wastes time, while those
being wrong destroys someone's notes silently.

Renames and retirements go in `migrations.json`, applied in version order before the diff:

```json
[{"version": "1.1.0",
  "renames": [["{vault}/aiOS/scripts/old.py", "{vault}/aiOS/scripts/new.py"]],
  "retires": ["{vault}/aiOS/templates/gone.md"],
  "note": "surfaced to the agent for follow-up a file copy can't express"}]
```

## License

Apache-2.0.
