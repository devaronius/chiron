# `skills/knowledge/`

The vault skills: everything that builds, checks or compiles an **ideaVerse**, plus the
installer that puts one in a repo.

The folder is a chiron-side filing convention only. Skills install **flat** — a skill filed at
`skills/knowledge/ideaverse-wiki-sync/` lands in a consumer repo as
`.claude/skills/ideaverse-wiki-sync/`, because that is where Claude Code discovers skills. The
category never reaches the target. The `ideaverse-` prefix is part of each skill's name: a repo
has skills of its own, and an unprefixed `note-review` or `wiki-sync` reads as if it belongs to
the project rather than to the vault.

| Skill | Answers | Owns |
|---|---|---|
| `bootstrap-ideaverse` | Put a complete ideaVerse in this repo, or bring an existing one up to the current framework | `tools/chiron-install.py` |
| `ideaverse-vault-health` | Is the vault well-formed? Broken links, orphans, duplicate basenames, frontmatter gaps | `vault-lint.py` |
| `ideaverse-contradiction-check` | Where does the vault disagree with itself, or with the code? | `contradiction-check.py` |
| `ideaverse-coverage-gap` | What does the vault not document at all — code, or its own cadence? | `coverage-gap.py` |
| `ideaverse-note-review` | Is *this one note* good — frontmatter, links, structure, sources? | `note-review.py` |
| `ideaverse-research-capture` | Does this new note pass, and where in the taxonomy does it belong? | `research-capture.py` |
| `ideaverse-modeling` | What *is* this thing, what should it be called, and what decision did we make? | — |
| `ideaverse-wiki-sync` | Is the compiled wiki stale, and how does it get reconciled? | `wiki-sync.py` |

`ideaverse-research-capture` is mechanical (does it pass? where does it go?);
`ideaverse-modeling` is conceptual (what is this, and what do we call it?). A new concept
usually wants `ideaverse-modeling` first, then `ideaverse-research-capture` to place the
result.

## Two things that are not like the others

**`bootstrap-ideaverse` is never installed into a repo.** It is listed in
`SKILLS_NOT_INSTALLED` in `chiron-install.py` and lives at user level instead — one copy for
every repo, either from the `chiron` plugin or copied by hand into `~/.claude/skills/`. A
per-repo copy is exactly how the previous version of it drifted from the payload it installs.
It is also the only skill here published as a plugin; see
[`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json).

**The other seven are payload, and payload is managed.** They ship with no project tokens, so
the installer's three-way diff upgrades them in place for as long as nobody edits them. Edit
one in a consumer repo and it becomes a permanent CONFLICT: the installer will report it on
every run and never overwrite it. Project-specific behaviour belongs in
`aiOS/aios.config.json`, and project-specific scripts in `aiOS/tools/ideaVerse/local/`, which
the installer never manages.

That is also why these seven are deliberately *not* in the plugin marketplace. A global plugin
copy would sit alongside the managed per-repo copy under a different namespace, and the one
you invoked would be a coin toss.

## Adding a skill here

1. `skills/knowledge/<name>/SKILL.md` — the frontmatter `description` is what routes an agent
   to it, so write it as a trigger, not a summary.
2. Add a row to the intent table in [`seeds/maps/skill-map.md`](../../seeds/maps/skill-map.md),
   including the Invoke column, which must match the skill's `disable-model-invocation`.
3. Write the CHANGELOG entry — a new skill is a **minor** bump — then
   `python3 tools/chiron-release.py --bump minor` to record its hashes.
4. `bash tools/selftest.sh` before committing.

Nothing needs editing for the skill to be found: the installer discovers a skill by the
presence of its `SKILL.md` at any depth under `skills/`.
