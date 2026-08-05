---
name: bootstrap-ideaverse
description: Install, adopt, upgrade or verify a chiron ideaVerse in a repo — the aiOS (ACE vault + maps + scripts + templates + librarian runbook), a wired concept wiki, and the framework meta-skills. Use when asked to "set up an ideaVerse / aiOS / knowledge vault here", to scaffold the docs vault + wiki, to bring an existing vault up to the current framework version, or to check whether one has drifted.
---

# Bootstrap IdeaVerse

Put a **complete, working ideaVerse** into a repo — the ACE vault (Atlas / Calendar /
Efforts), the `aiOS/` operating layer, a compiled `wiki/` that is *in sync* on the first
run, the framework meta-skills, and the orientation wiring so any agent landing in the repo
finds it. And keep it current afterwards.

The payload is **not** bundled here. It lives in
[chiron](https://github.com/devaronius/chiron) and this skill fetches it, so there is
exactly one copy of the framework and it cannot silently drift from what a repo has
installed. `tools/chiron-install.py` in that checkout does the mechanical work; your job is
the interview, the judgment calls, and the semantic merges a script cannot make.

## Step 1 — Refresh the chiron cache

```bash
if [ -d ~/.chiron/.git ]; then git -C ~/.chiron pull --ff-only
else git clone --depth 50 https://github.com/devaronius/chiron ~/.chiron; fi
cat ~/.chiron/VERSION
```

If the network is unavailable and `~/.chiron` already exists, say so and continue with the
cached copy — naming the version you are working from. If it does not exist and you cannot
clone, **stop**: there is no payload to install, and inventing one is worse than nothing.

## Step 2 — Detect the mode

Run the plan. It tells you which of four situations you are in; do not guess from a
directory listing.

```bash
python3 ~/.chiron/tools/chiron-install.py --target "$REPO" --plan
```

| Mode | Situation | What you do |
|---|---|---|
| **install** | no vault | interview (Step 3), then apply |
| **adopt** | vault, no manifest | classify, apply the safe part, report the rest |
| **upgrade** | manifest older than chiron | migrations + three-way diff |
| **verify** | manifest current | report drift; write nothing |

Each file lands in one of six buckets. Understand them before you show a plan:

- **ADD** — missing here; will be written.
- **UPDATE** — provably unmodified since it was shipped, so overwriting loses nothing.
- **CONFLICT** — you changed it. Never overwritten. Yours to reconcile.
- **REVIEW** — a `seeded` file (the briefing, the maps, `aios.config.json`, the wiki
  baseline). Written once at install, then yours forever; upstream has moved but the
  installer will not touch it. **This is where you come in** — see Step 6.
- **RETIRE** — dropped upstream and pristine here; will be deleted.
- **KEEP** — dropped upstream but you modified it, so it stays.

## Step 3 — Interview (install mode only)

Ask one at a time and recommend a default. Skip entirely for adopt/upgrade/verify — those
read their answers from the existing manifest.

1. **Project name & one-line identity** — e.g. "Acme Checkout — the payments service for the Acme storefront."
2. **Domain** — 2–3 sentences on what the project *is* and does. Seeds the briefing's "What this is".
3. **Roles the agent works with** — e.g. "Dev, QA, PO", or "just me (solo)". If solo, the Roles section is omitted entirely.
4. **Where the vault lives** — `docs/` (recommended when the repo also holds code — it keeps the vault clearly separate) or the **repo root** (for a notes-only repo, where the repo *is* the Obsidian vault). Root mode passes `--at-repo-root`, which also writes a single combined `CLAUDE.md` instead of two.
5. *(mention only)* The briefing note is `project-brief.md` by default. Offer to name it after the project instead — `--briefing-note acme` gives `acme.md`, which reads better as a `[[wikilink]]` — and the choice is recorded so upgrades follow it.

## Step 4 — Show the plan, then apply

**Never apply without showing the plan first.** Summarise it in prose — counts per bucket,
and every CONFLICT and REVIEW named individually, since those are the ones with
consequences. Then get confirmation.

Before applying anything to an existing vault, take a baseline so you can prove you did no
harm:

```bash
python3 "$VAULT/aiOS/scripts/vault-lint.py" --quiet    # keep this output
```

Then apply, passing the interview answers on install:

```bash
python3 ~/.chiron/tools/chiron-install.py --target "$REPO" --apply \
  --project-name "…" --project-domain "…" --roles "Dev,QA"        # install only
```

Use `--map SRC=DEST` when a consumer has renamed something chiron ships — e.g.
`--map skills/knowledge/wiki-sync=.claude/skills/cca-wiki-sync`. SRC is the payload path in
the chiron checkout, category folder included. The rename is recorded in the
manifest so every later upgrade follows it instead of re-adding the original name.

## Step 5 — Verify, and never launder drift

After applying:

```bash
python3 "$VAULT/aiOS/scripts/vault-lint.py"     # compare against the Step 4 baseline
python3 "$VAULT/aiOS/scripts/wiki-sync.py"      # report drift — see the warning below
python3 "$VAULT/aiOS/scripts/open-items.py"     # safe: a pure function of the notes
```

- If the linter is dirty **and was clean before**, that is the upgrade's fault. Say so
  plainly and fix it rather than reporting success.
- **On a fresh install only**, snapshot the wiki baseline once:
  `python3 "$VAULT/aiOS/scripts/wiki-sync.py" --update`, then confirm it reports
  *"Wiki is in sync"*.
- **On upgrade or adopt, never run `--update`.** It re-snapshots *every* source, so running
  it while unreconciled drift exists silently baselines that drift and hides it forever —
  and an upgrade is the worst possible moment, because the tooling underneath just changed.
  Report the drift and hand off to the wiki-sync skill.

## Step 6 — Merge what the script could not

This is the part only you can do. For each **REVIEW**, diff the installed file against the
upstream one and merge *semantically*:

```bash
diff "$VAULT/aiOS/maps/skill-map.md" ~/.chiron/seeds/maps/skill-map.md
```

A consumer's `skill-map.md` grows its own rows and precedence rules; upstream adds framework
sections. Fold the new framework material in and **keep every local rule intact** — the
whole reason these files are never overwritten is that the local content is the valuable
half. Show the user what you propose to merge before writing it.

Also surface any migration `note` from the plan: those describe consequences no file copy
expresses (a changed snapshot format, a new frontmatter field) and usually imply follow-up
work.

## Step 7 — Wire repo-root orientation (install mode, non-destructive)

So an agent landing at the repo root finds the vault:

- If `./CLAUDE.md` **does not exist**, create it with a short `# <PROJECT>` heading and a
  `## Knowledge base` section pointing at the briefing and the two maps.
- If it **exists**, append that `## Knowledge base` section. **Never rewrite or reorder
  existing content** — append only.
- In **root mode** the vault's `CLAUDE.md` *is* the repo's; skip this step.

## Step 8 — Report & hand off

State the mode, the version installed, what changed, and — explicitly — what you left alone
and why. Then suggest the next step rather than taking it:

> Your ideaVerse is live at `<vault>/` on chiron `<version>`. To start capturing domain
> terms, decisions and API contracts, use the **`domain-modeling`** skill; to compile them
> into the wiki, **`wiki-sync`**.

## Guardrails

- **Show the plan before writing.** Every mode, every time.
- **CONFLICT files are never touched.** If the user wants one reset, they ask for it explicitly.
- **`wiki/` is generated.** Never hand-edit it; never `--update` outside a fresh install.
- **Configure, don't edit.** Project-specific behaviour belongs in `aiOS/aios.config.json`;
  scripts stay byte-identical to upstream so they can keep being upgraded. An edited script
  becomes a permanent CONFLICT. Project-specific scripts go in `aiOS/scripts/local/`, which
  the installer never manages.
- **This skill is user-level.** It belongs in `~/.claude/skills/`, one copy for every repo.
  Do not commit it into a target repo — a per-repo copy is exactly how the previous version
  of this skill drifted from its own payload.
- **Report honestly.** If Python is missing, the clone failed, or a step was skipped, say
  so. A silent omission reads as "nothing was wrong".
