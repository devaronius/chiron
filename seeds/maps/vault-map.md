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

- **{{BRIEFING_NOTE}}** — `{{VAULT_PREFIX}}{{BRIEFING_NOTE}}.md` — your brief on what {{PROJECT_NAME}} is and how to interact
- **vault-map** — `/aiOS/maps/vault-map.md` — this file
- **skill-map** — `/aiOS/maps/skill-map.md` — every skill you can use on my behalf

`aiOS/` sits at the **repo root**; the notes sit in the **vault** (`{{VAULT_ROOT}}`). A command below is written from the repo root; a path like `ideaVerse/…` is vault-relative. Harness-specific entry points (`CLAUDE.md`, `AGENTS.md`) sit at the repo root and are not vault notes.

**This map states rules, not history.** The incident behind a rule — counts, dates, what broke — belongs in the note that owns it, not here.

## Wiki compilation

### Default write locations

- Topic hubs: `wiki/topics`
- Concepts: `wiki/concepts`
- Entities: `wiki/entities`
- Projects: `wiki/projects`

### Compilation scope

Compile from the whole `ideaVerse/` vault; which kind of note lives where is the folder taxonomy below, and is not restated in the wiki skill. Two areas need explicit handling:

- **`efforts/projects/` → `wiki/projects`** — compile each project (scope, status, deadlines) to a project note.
- **`calendar/days/`** — do **not** create per-day wiki notes; the wiki is not interested in the day itself. **Mine each day** for documentation-worthy content — issues reported, deadlines defined, decisions taken — and fold those into the concept / entity / project notes, which then cite the day note as a source. A day with nothing doc-worthy produces no wiki change.

## Folder structure

The vault follows the **ACE** framework — Atlas = the mind's landscape, Calendar = the mind's rhythm, Efforts = the mind's output.

- `atlas/` — the timeless knowledge landscape:
	- `apis/` — raw Swagger/OpenAPI **clippings**, one per backend service, named `<service>_api.md`. Each pairs with a compiled entity note at `wiki/entities/<service>-api.md`. The clipping is verbatim — the code is the final authority on field shapes. **Read the entity note, not the clipping**: clippings run to tens of thousands of words, so open one only to check a specific schema, and `grep` it rather than reading it whole.
	- `concepts/` — the project's ubiquitous language and how its code behaves, one term per note, from the [concept template](/aiOS/templates/concept.template.md) and maintained through the **ideaverse-modeling** skill. **Two kinds only**, declared as `kind:` in frontmatter:
		- **`domain`** — a term from the business's own vocabulary.
		- **`behaviour`** — how our code works: its rules, its gotchas, its open questions.
	  Not concepts: a **dated check or investigation** goes to `calendar/research/`, and its one durable rule moves into the behaviour concept it belongs to. **How the team works** — the board, the work-item lifecycle, commit conventions — is a human process and goes to `documents/` as `kind: process`. Exception: `open_item` is a framework note and stays here. **Enforced:** `vault-lint` reports a missing or unknown kind as `[CONCEPT-KIND]`, and `research-capture.py check` fails on it.
	- `documents/` — **the last resort, with a closed list of kinds.** A note goes here only if no other atlas folder fits *and* it is one of four kinds:
		- **External** — a system, team, vendor or device we don't build but depend on.
		- **Process** — how *people* do something, step by step, written for humans. If an agent also carries out the process, the `aiOS/runbooks/` runbook owns the steps and the document gives the human context, **linking to the runbook rather than repeating it**.
		- **Stakeholder reference** — written for readers outside the team and meant to be handed over.
		- **Backend request** — an ask to another team plus its resolution. An endpoint's wire contract stays single-sourced in its `apis/` clipping and `wiki/entities/` note; a request record **points to it, never restates it**.
	  **Enforced:** every note here carries `kind: external | process | stakeholder-reference | backend-request`. `vault-lint` reports a missing or unknown kind as `[DOC-KIND]`. Relevance is not machine-checked; the filer decides.
	- `personas/` — user **personas**.
- `calendar/` — the rhythm: `days/`, `briefings/`, `meetings/`, `research/`, `releases/`, `sprints/`.
	- `research/` — dated findings: research tickets, upgrade and toolchain checks. **Distil at review time, not later:** the moment a research note is reviewed, its durable rule goes to the atlas note that owns the subject, and the research note stays as the dated record. Research is reached by date or by the note that cites it, never read as current truth — a research note nothing links to is one whose findings were never distilled, and `vault-lint` reports it as `[ORPHAN]`.
- `efforts/` — the output:
	- `projects/` — long-running **projects**; compiled to `wiki/projects`.
	- `works/` — discrete design/build **efforts**, each carrying a `status:` frontmatter field — one of `active · shipped · superseded · reference`. There is deliberately no `blocked`: a stuck effort stays `active` with a `[status:: blocked]` open item inside it (see [[open_item]]). New works notes start from the [work template](/aiOS/templates/work.template.md).
	- `referrals/` — **outbound artefacts written for a reader outside the team** (design, backend, product, legal), handing them something only they can resolve. Because the reader is external: **no `[[wikilinks]]` in the body** — they cannot resolve them, so links go in frontmatter only — no board or repo jargon, and `audience:` in frontmatter. Still vault notes: required frontmatter applies, and each must be linked from the effort it serves or `vault-lint` reports `[ORPHAN]`. Keep the *decision* in the driving `works/` note; a referral is the message, not the record.
- `+/` — inbox (unfiled capture). **Temporary by design:** a note here moves out when processed. File a note before editing or linking to it — `vault-lint` reports filed notes that link into the inbox as `[INBOX-LINK]`.

### Which atlas folder does this go in?

`concepts/` and `documents/` are **subject-anchored** — you choose where a subject belongs.

| What you have | Goes in |
|---|---|
| How something *behaves*, its gotchas, a domain term | `atlas/concepts/` |
| A process, an external party, a request record | `atlas/documents/` |
| A raw Swagger/OpenAPI dump | `atlas/apis/<service>_api.md` |
| A kind of user, and what they need | `atlas/personas/` |
| Our own build work, with its journey and reversals | `efforts/works/` |

> **Optional: code-anchored folders.** A vault sitting beside code can add folders whose shape is dictated by the repo rather than chosen — one note per package, per app, or per feature directory, with the note's basename matching the directory's. That 1:1 is what lets `coverage-gap.py` check coverage mechanically. Add them here when you introduce them, and record the directories under `code` in `aiOS/aios.config.json`.

The overlap to watch is **two folders describing the same subject through different lenses**. Each must stay in its lane; a note that starts restating another lens belongs in that other note instead. The failure mode is not duplication but divergence — the copy drifts, the vault ends up asserting two different things about one subject, and the copy is usually the one that is wrong.

## Retiring a shipped effort — distill, then demote

When a `works/` note reaches `status: shipped`, its knowledge is in the wrong place: a reader asking *"how does this work now?"* looks in `atlas/`, not in an effort's journey. Retiring it is a **distillation**, not a cleanup.

**Never delete the file; shrink it to a stub.** An effort note is cited as a wiki source, sometimes the only one, so deleting it orphans the compiled note and breaks every link. But the full journey is too expensive to keep reading — soon after shipping, most of it has drifted from the code or is more detail than anyone needs. The durable knowledge moves to atlas; the note becomes a stub that keeps its links resolving, and the full text stays one `git show` away.

**When:** set `shipped: <date>` as `status:` becomes `shipped`. The note stays whole for the number of workdays in `efforts.stubAfterWorkdays` (`aios.config.json`, 14 by default) — long enough to cover the rest of its sprint and the next. After that `vault-lint` reports `[INFO] RETIRE` and the librarian lists it. **The stub is written in a session with a human present, never unattended.**

Five steps, in order:

1. **Split the content.** Steady state ("it works like this", "this constant means that") goes to atlas. The journey's **lessons** ("we considered X, rejected it because Y", "this reversed mid-build") become **Decision blocks** in the atlas note that owns the subject, each naming the rejected alternative and why. Everything else — session logs, step-by-step progress, superseded plans — is not carried over.
2. **Verify every claim against code before moving it.** Not optional. A shipped note records what was *decided*, which is not always what was *built*. Promoting a stale claim into atlas is worse than leaving it in a note marked shipped, because atlas is where people look for current truth.
3. **Write into the atlas note that already owns the subject.** Only create a new note when no owner exists — a second note on an owned subject drifts, and the duplicate is the copy nobody re-verifies.
4. **Replace the effort note's body with a stub.** Keep the frontmatter (add `stub: <commit>`, the hash of the last full version) and write only:
   - one paragraph of **outcome**: what shipped, and explicitly **what did not survive the build** (often the most valuable sentence the retired note carries);
   - a **pointer to each atlas note** the knowledge moved to;
   - the line `Full history: git show <commit>:<path>`.
   Aim for about 100 tokens. Open items it still owns must be re-homed first (see [[open_item]]).
5. **Recompile** with **ideaverse-wiki-sync**, and correct the wiki note too — it usually repeats whatever the source got wrong.

> [!warning] Step 2b — re-measure forecasts, never copy them
> Step 2 catches a claim that was wrong when made. It misses one that was **right when made and has since expired** — the class a retirement pass actually promotes, because the work ships after the sentence is written and nobody edits it.
>
> **Detect.** Treat every sentence carrying one of these as a forecast, not a finding:
> `## Out of scope` · `known consequence to watch` · `until this is addressed` · `for now` · `leave it in place` · `retire it later` · `still references` · `surface this when picking up the follow-up`
>
> **Why it slips through:** atlas is present-tense, so distilling strips the hedge. *"Until addressed, X renders the wrong colour"* becomes *"X renders the wrong colour"* — same words, now a finding.
>
> **Act — two outcomes, never a third.** Re-measure against code: came true → write it past-tense with today's counts. Did not come true → **do not promote it**; record "this risk did not materialise" in the effort note. Copying it across unchanged is the failure. If you cannot re-measure it, leave it behind.
>
> Keep the original sentence in the effort note under a correction callout — a reader arriving at the retired note needs the correction attached to what misled them.

Some efforts turn out to be **already distilled** — their durable half went to atlas as it was built. Those need only the pointer. Say so, rather than leaving a reader wondering whether the move was missed.

## Folder hubs

A folder with many notes carries a hub note **named after the folder** — `concepts/concepts.md`, `documents/documents.md` — indexing its children in a table. Child notes point at it with `up: ["[[concepts]]"]`.

> **Never name a hub `README.md`.** Wikilinks resolve *by basename*, so several `README.md`s collapse into one unresolvable name: a wikilink to `README` can't work, nothing can link to them (they all lint as `[ORPHAN]`), and `up: ["[[…]]"]` dangles in every child.

## Why the naming matters

**Note basenames must be unique within the vault, and within the wiki.** They are *not* unique across the two, and deliberately so: `wiki-sync.py` keys sources by basename, so a compiled wiki note mirrors the name of the source it was compiled from. A `[[link]]` to one of those pairs is therefore ambiguous between a source and its own compiled summary, which is tolerated because they are the same subject. `vault-lint.py`'s `[DUPE]` check is vault-scoped for this reason, and `research-capture.py check` compares a candidate against the vault only — pointing it at a `wiki/` file would flag every pair. Do not "fix" either by widening the scope.

Within each of those two trees, uniqueness matters for two reasons:

- **Wikilinks resolve by basename**, regardless of folder. Two notes sharing a name means every `[[link]]` to it lands on whichever the resolver picks.
- **The tooling resolves by basename too.** `wiki-sync.py` keys sources by basename, and `coverage-gap.py` looks package and feature notes up as bare basenames. **Rename a note and you may silently open a coverage gap.**

On a collision, the **more general / product-domain** meaning keeps the bare name and the **more specific** note takes the qualified one — `onboarding` for the product's first-run flow, `onboarding_developer` for the human process.

**A duplicate is worse than it looks.** A second note on an owned subject does not merely repeat it — it **drifts**, and the duplicate is the copy nobody re-verifies against the code. Prefer extending the owning note over adding a second one.

Run `python3 aiOS/tools/ideaVerse/vault-lint.py` after adding notes — it reports basename duplicates as `[DUPE]`.

## Frontmatter dialects and link scope

**Wikilinks resolve across the whole vault and `aiOS/`, not just `ideaVerse/`.** `[[vault-map]]` is this map, `[[{{BRIEFING_NOTE}}]]` is the briefing note, and a compiled summary lives in `wiki/`. Resolving against `ideaVerse/` alone reports mostly false broken links.

**Two frontmatter dialects are valid**, and a single required-field set wrongly fails one of them:

| Dialect | Required | Where |
|---|---|---|
| standard | `up`, `related`, `created` | most notes |
| clipping | `title`, `source`, `created` | `atlas/apis/` (tagged `clippings`) — source-traceability is satisfied by `source:` **singular** |

## Generated files, and lint tuning

`wiki-sync.py` is the **sole writer** of `wiki/`, and `open-items.py` the sole writer of `open-items.md`. Never hand-edit either. `vault-report.py` regenerates sections 1–5 of `vault-report.md` and **replaces §6** — do not run it while a librarian's proposals stand there unrecorded.

**Every exemption in `vault-lint.py` / `contradiction-check.py` was added to kill a measured class of false positive.** Reverting one brings that class back. Record why each exists, and read that record before relaxing any checker.

## Leave is declared, not backfilled

`coverage-gap.py` wants a day note and a briefing for every Mon–Fri since the first one exists. Across a holiday that is dozens of gaps for days nobody worked, and both instinctive answers are wrong: writing empty notes to satisfy a checker, or learning to scroll past the section — which is how a real gap gets missed.

Declare the absence instead, in `aios.config.json` → `calendar.absences`:

```json
"calendar": { "absences": [
  { "from": "2026-08-22", "to": "2026-09-14", "why": "on leave — see the handover note" }
] }
```

Both ends inclusive; `why` is required by convention, not by the parser. Every run prints each range and the days it removed — a checker that silently reports less is worse than one that reports too much. A malformed entry is dropped, so a typo surfaces as the gaps it failed to hide.

**Declare the range when the leave is planned**, alongside the handover note. Reconstructing it afterwards from memory is when the wrong dates get written down.

## What becomes an open item

An `[status:: open]` line is a claim that *this project* owes something. Filter at the point of writing, not later:

- **Confirm it is ours before recording it.** An issue is not yours just because it is unassigned and visible in a channel you are in. A chat you share with the wider organisation carries a constant stream of other teams' bugs; pulling those in makes the ledger useless as a picture of what you owe.
- **A ticket tagged with your team's name is a claim to verify, not a fact.**
- **An ask whose prerequisite has not landed is not yours yet** — it sits with whoever owns the prerequisite.
- **Routine housekeeping is not tracked work.** Merging your own stranded branches, gitignoring stray files, pulling a behind checkout — leave them out; they bury the items that matter.

Narrow this rule to your project's actual scope — the repo paths, the team, the product surface — so a reader can apply it without asking.

## Notes that live outside the vault

Some collections sit beside the ideaVerse rather than inside it. They are not part of the ACE structure, but they still follow the vault's note conventions (templates + frontmatter):

- `wiki/` — the **{{PROJECT_NAME}} concept wiki**: organized by concept (`topics/`, `concepts/`, `entities/`, `projects/`), synthesized from the raw notes in `ideaVerse/`. Entry point: `wiki/index.md`; machine-readable catalog: `wiki/wiki.catalog.jsonl`. Every note uses the [base template](/aiOS/templates/base.md) frontmatter (`up`/`related`/`created`).

  > **The wiki is generated, never hand-edited.** It is a compiled summary layer; the `ideaVerse/` notes are the source of truth, and every wiki note traces back to a source via its `Sources:` line. To change wiki content, **do not edit `wiki/` directly** — write the data into the best-fit `ideaVerse/` source (or, if none fits, **create a new `ideaVerse/` note** in the right ACE location), then run **ideaverse-wiki-sync**, which detects drift, (re)compiles the affected notes, updates the catalog, and re-snapshots the baseline. A wiki-file write is only ever the *output* of that compile step.

  Drift detection on its own: `python3 aiOS/tools/wiki/wiki-sync.py` reports ideaVerse sources that were added/changed/deleted and need (re)compiling (baseline in `wiki/.wiki-sync.json`); `--update` re-snapshots after reconciling.

## How to create notes properly

Always use a template in `/aiOS/templates`. When in doubt, use the [base template](/aiOS/templates/base.md), which carries the REQUIRED YAML fields every note starts with — `up`, `related`, `created` — plus `updated`, `tags`, `sources`, `aliases`, which are conventional and usually wanted.

- [base](/aiOS/templates/base.md) — the required-frontmatter starting point for any note.
- [concept.template](/aiOS/templates/concept.template.md) — a canonical domain-term / concept note (`atlas/concepts/`): base frontmatter + `aliases`/`sources`, a bold one-line definition, a "Not to be confused with" disambiguation, an open-questions callout, and an optional Decision block. Maintained via the **ideaverse-modeling** skill.
- [work.template](/aiOS/templates/work.template.md) — a discrete design/build effort (`efforts/works/`), carrying `status:` and its journey.
- [api-note.template](/aiOS/templates/api-note.template.md) — a Swagger/OpenAPI clipping (`atlas/apis/`), which uses the **clipping** dialect; capture steps in [api-note.runbook](/aiOS/runbooks/api-note.runbook.md).
- [day-note.template](/aiOS/templates/day-note.template.md) — a daily note (`calendar/days/<date>.md`); how to build it is in [day-note.runbook](/aiOS/runbooks/day-note.runbook.md).
- [daily-briefing.template](/aiOS/templates/daily-briefing.template.md) — the morning briefing (`calendar/briefings/<date>.md`); build steps in [daily-briefing.runbook](/aiOS/runbooks/daily-briefing.runbook.md).
- [sprint-note.template](/aiOS/templates/sprint-note.template.md) — merging a closed sprint's day and briefing notes into one (`calendar/sprints/`), with a stakeholder summary alongside the engineering detail; build steps in [sprint-note.runbook](/aiOS/runbooks/sprint-note.runbook.md).
- [research.template](/aiOS/templates/research.template.md) — a dated investigation (`calendar/research/`): question, constraints, **Method**, findings, options, recommendation, **Limitations**, open items. **Method and Limitations are not optional** — a research note is the kind most likely to be read by someone who cannot ask the author anything, and a claim whose provenance and caveats are missing cannot be weighed.
- [schedule.template](/aiOS/templates/schedule.template.md) — a scheduled routine spec (`/aiOS/schedules/`), including how to retire one without leaving the real scheduler firing it.

> This convention applies to vault notes **and** to the external collections listed above (e.g. `wiki/`).

### What `created:` and `updated:` mean

- **`created:`** — the date the note was first written. It never changes.
- **`updated:`** — the date the file was last **touched**, not the date its ideas last changed. Bump it in the *same commit* as any edit to the note, however small — a frontmatter-only fix counts.

`vault-report.py` enforces this by comparing `updated:` against the note's last git commit date, so the two agree only if you bump the field in the commit that touches the file. The alternative reading — "the date the content last changed" — makes the check permanently circular: committing a fix re-flags the note it just fixed.
