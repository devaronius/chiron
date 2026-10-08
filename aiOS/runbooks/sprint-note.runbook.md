---
up: []
tags: ["runbook", "sprint-note"]
related: ["[[sprint-note.template]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["Sprint Note Runbook"]
---

# Sprint Note — Assembly Runbook

Instructions for merging a closed sprint's week/day/briefing notes into one **sprint note**. This is the **runbook**: it says how to build it. The output skeleton it fills lives in [[sprint-note.template]].

> **Audience:** the team *and* stakeholders (POs, business). Unlike the day note and the daily briefing, this note is read by non-engineers too — see the "For stakeholders" rule below.

## When this runs

At the end of a sprint, on request — not scheduled. **Take the sprint's name from the tracker, never from arithmetic.** Numbering that resets on a cycle boundary (per quarter, per release train) is common, so "sprint 7" may be followed by "sprint 1"; verify what people actually call the *next* sprint in chat or tickets before writing a heading or a "carried into" section.

**Sprints are counted in workdays — Monday to Friday.** A tracker usually stores calendar boundaries, so a ten-workday sprint ends on the trailing weekend; its real last day is the Friday before. Take the boundaries from the tracker, then trim both ends to workdays before writing `coverage`, the `# ` heading or any "n days" count. A gap at the end of a sprint is measured in workdays too — two empty weekdays is two, not four.

## Inputs (where to look)

Given a sprint's date range (`<start>` → `<end>`):

1. **Day notes** — `ideaVerse/calendar/days/<date>.md` for every date in range.

   > **There is no week-note tier.** `calendar/` holds `days/`, `briefings/`, `meetings/`, `research/` and `sprints/` only: a sprint spans exactly two aligned ISO weeks, so a week note is half a sprint note on the same boundaries. Day notes link their sprint note directly.
2. **Daily briefings** — `ideaVerse/calendar/briefings/<date>.md` for every date in range. Briefings often carry richer **trend** data (several dated snapshots of the same metric) than the day notes, which only paste a snapshot on the day it was pulled — read every in-range briefing even where it looks redundant with a day note.
3. **The repo, as evidence the notes cannot contradict.** The dailies are written at 09:00 and can only see what already happened; the repo records the rest. Check all of it:
   - `git log --all --since=<start> --until=<end+1>` including **weekend dates** — confirm whether the sprint really ends on its last working day.
   - the changelog — a dated release section is a **release that happened**, and it is frequently absent from every day note.
   - the version manifest's history (`git log -S'version'`) — a version bump dates the release cut, which may land *after* the sprint boundary even when the release did not.
4. **The previous sprint note** — read it before writing. It, not this runbook, is the authority on format: how the opening paragraph reads, whether the sprint takes one `## Headline:` section or several, and the `<div style="break-after: page;"></div>` page breaks that precede each major section for PDF export.

   > **No previous note yet?** With `calendar/sprints/` empty there is nothing to match, so follow [[sprint-note.template]] and let the first note set the house format. From then on the most recent note is the authority, not this runbook.
5. Do **not** pull in notes outside the requested range, even if adjacent (e.g. a briefing for the day the *next* sprint starts stays put) — but do read it, because it often states what the last in-range day actually produced.

## Ask the user before writing — the dailies are not complete

**The single biggest failure mode of this runbook is treating the day notes and briefings as a complete record.** They are not, and their gaps are systematic rather than random: the daily runs are unattended, they see the repo and (when the connector works) chat, and they are blind to anything that happened in the evening, in a meeting, or verbally. In the Q3 Sprint 3 assembly, **three material facts were absent from all twenty in-range notes** and surfaced only when the user read the draft — including the sprint's actual closing event, a release of both apps.

Before writing, ask the user directly. Each of these has been wrong at least once:

| Ask | Why the notes miss it |
|---|---|
| **Did anything get released or uploaded — any app, any environment?** | Builds go out at the end of the day, after the last daily run; the version bump and changelog stamp are often committed days later. |
| **Did any "waiting on design/backend" item come back?** | An answer given verbally or in a meeting never reaches the repo. A daily copies `[status:: blocked]` forward mechanically, so a resolved item can look blocked for weeks. |
| **Is anything on the carried-open list already done, or not ours?** | Same mechanism, opposite direction. Verify before publishing a list that says a team has been waiting a month. |
| **Did anything ship that has no ticket and no commit?** | Videos, documents, demos, calls. Work that consumed days can appear in no commit at all. |

Do not present this as a questionnaire — ask what you cannot verify, and verify what you can first (a "blocked on design, then mobile implements" item can be tested with `git log -- <the files it would touch>` since the raise date; no commits means it was genuinely never built).

## Process

1. **Synthesize, don't concatenate.** Read every input fully, then write one cohesive narrative grouped by theme (headline effort, releases, QA, decisions, reliability, engineering, open items) — not a day-by-day transcript. Preserve decision wording and attribution.
2. **Open on the sprint, not on the note.** The paragraph under the `# ` heading is the first thing anyone reads: it states what the sprint *was* and what came of it — the throughline, what shipped, what didn't, and the next sprint's name. Which notes were merged is **one closing clause at most** an opening paragraph that spends its length on which files were folded in and where their sources went is a work log, not a sprint overview.
3. **Narrative carries the story; tables carry the inventory.** A headline section that enumerates ten tickets inline reads as a data dump even to an engineer. Put the ticket-by-ticket record in a table (`# | the question | what was decided`) and let the prose do what a table cannot: the problem in human terms, the finding that changed the plan, the decision that turned on a fact rather than a preference. Pull two or three items back out of the table and tell them properly — the reversal, the near-miss, the thing verified instead of argued.
4. **Name a headline for what changed, not for how the work went.** "The app learns to start without the network" over "offline translations, decided and built in one sprint". A sprint may take several `## Headline:` sections or one — follow the sprint's actual shape.
5. **No commentary about the note itself.** The reader wants the sprint, not its editing history. Never write that an item "moved to the section below", that a list "used to contain" something, or that the daily sources disagree with what you just wrote. Provenance belongs in frontmatter `sources`; a firsthand fact gets the vault's normal attribution (*Per <name>, <date>*) and nothing more.
6. **Verify carried open items — do not transcribe them.** Every blocked item inherited from the dailies is a claim that someone has been waiting since `[raised::]`. Check it: does the code show the work already done, has the dependency landed, is it even this team's? Publishing a stale wait is worse than omitting it, because it sends someone to chase a colleague who already answered.
7. **Reliability section.** If any input pulled a monitoring snapshot (crash rates, error budgets, engagement), build one row per snapshot date — not just first and last — so the trend is visible, and render it as a `mermaid xychart-beta` line chart beside the table: Obsidian renders Mermaid natively and it stays plain text, diffable and with no binary assets in the vault. Spell out acronyms on first use, either inline or as the row label.
8. **"For stakeholders" section.** Write a short plain-language section near the top, before the technical detail: what shipped and why it matters, releases, QA/blockers resolved, stability/engagement trend in plain terms, what's open, what's next. No stack traces, commit hashes, ticket numbers as the primary noun, or internal code identifiers — describe the user-facing behaviour instead. Keep the detailed engineering sections below unchanged for source-traceability; this is an additional layer, not a replacement.
9. **Group open items by the discipline that must act** — design, backend, this team, other — mirroring the daily briefing's convention, rather than leaving one flat list. Name the next sprint correctly (see numbering note above) in the section heading.
10. **Don't fabricate.** Every figure/decision/deadline traces to a source. If the user or a concurrent edit adds a fact you can't trace to an input note (e.g. a release the sources don't mention), don't silently drop it — it may be something the user knows firsthand; leave it and fold it in naturally rather than deleting or ignoring it.

## Deleting the merged source notes

Merging implies the source week/day/briefing notes get **deleted** once folded in — but this has real blast radius, so **confirm with the user before deleting** if you haven't already on this note:

1. Search the whole vault for `[[wikilinks]]` and path references to each source file being deleted — not just inside `ideaVerse/`, also `wiki/`.
2. **The `wiki/` fallout is the big one.** Compiled wiki notes cite raw sources in their `**Sources:**` line, and `wiki/wiki.catalog.jsonl` mirrors this in each row's `sources[]` array (matched by bare filename stem, e.g. `"2026-07-02"` — ambiguous between a day note and a briefing sharing that date, so re-check what's actually still being cited after your edit). For every wiki note/catalog row that cites a file you're deleting: replace that citation with a link to the new sprint note (`[Q... sprint N.md](../../ideaVerse/calendar/sprints/Q...%20sprint%20N.md)`), deduping if the sprint note is already cited there.
3. Notes outside `wiki/` (e.g. `ideaVerse/efforts/projects/*.md`, other briefings) may also link the deleted dates. These are often historical/point-in-time citations (a briefing quoting "carried from the 2026-06-30 day note"). Write example dates as plain text, never as live wikilinks — a wikilinked example in this runbook breaks the moment a sprint merge deletes that date, which is exactly what happened to the one that used to be here. Treat these as lower-priority than the wiki, and call out what's left un-fixed rather than silently rewriting a large number of unrelated files.
4. **Re-home the open items you are about to delete — the step that is easiest to miss, because nothing fails when you skip it.** A day note may be the *only* note carrying a given `[status:: open|blocked]` line, and `open-items.py` builds the live ledger by scanning those lines. Delete the note and the item silently leaves `open-items.md` — it does **not** survive in the sprint note, because a sprint note's "Open, carried into …" list is deliberately plain `- [ ]` prose with no `[status::]` metadata, which the parser ignores by design.

   ```bash
   # before deleting — capture the baseline and the items at risk
   grep -c '^| ' open-items.md
   grep -h '\[status:: *\(open\|blocked\)' ideaVerse/calendar/{days,briefings}/<dates>.md
   ```

   For each such item, find whether a **surviving** note already owns it, and re-home the ones that don't:
   - Effort-specific → its `efforts/works/<effort>.md` or `efforts/projects/<project>.md`.
   - Tied to no effort → the standing operations project note, whose whole purpose is to own exactly these.
   - **Exception — items a tracker already owns.** An item that exists as a ticket on the board is tracked there; a day note lifting it into the ledger is daily surfacing, and that lift is *meant* to expire with the day note. Don't re-home those — but say so, rather than leaving it ambiguous whether they were dropped or excluded.

   Carry the `[raised::]` date forward unchanged; the item's age is the point of tracking it. Re-run `open-items.py` afterwards and **compare the row count to the baseline** — a drop is expected (day notes restate the same item daily, so duplicates collapse), but every *distinct* item that vanished must be one you re-homed or consciously excluded.

5. Delete the source files. Some harnesses gate file deletion behind a permission the session has not been granted yet — ask for it rather than working around it.
6. Run `python3 aiOS/tools/wiki/wiki-sync.py` to see the drift, reconcile any real gaps (step 2), then `python3 aiOS/tools/wiki/wiki-sync.py --update` to re-snapshot the baseline. Run the plain check again afterward and confirm it reports 0 new/changed/deleted (pre-existing unrelated drift, e.g. never-compiled briefings, is fine to leave — call it out, don't silently absorb it into a "clean" baseline).
7. Re-run `python3 aiOS/tools/ideaVerse/open-items.py --today <date>` so the ledger matches the owning notes.

## Output

Write to `ideaVerse/calendar/sprints/<sprint name>.md`, filename matching the note title. Use the frontmatter from [[sprint-note.template]]: `coverage` as `<start>..<end>`, `created`/`updated` as the sprint's start and end dates, and every external source (chat threads, work items, design files, git commits, console URLs) consolidated in `sources` — internal ideaVerse notes that survive (projects, concepts, other sprint notes) go in `related` as `[[wikilinks]]` instead.

## Rules

- **Source-traceable.** Every figure/decision/deadline traces to a source (day note, briefing, or an external link). No source → say so.
- **The dailies are inputs, not the truth.** They are unattended 09:00 snapshots: blind to evenings, meetings and anything said out loud, and they copy stale statuses forward without re-checking. Cross-examine them against the repo and against the user before publishing anything they assert — especially a release that "did not happen" and a blocker that has "been open for weeks".
- **Write for a reader who was not there.** No commentary on the note's own construction, no navigation instructions between its sections, no arguments with its own sources. If a sentence would not make sense to a PO reading this in six months, it belongs in frontmatter or nowhere.
- **Expect a review pass.** This note is read closely by the person who lived the sprint, and the first draft has never survived it intact. Hand over a draft and invite correction rather than presenting it as finished — the corrections are the point, and they are usually facts no source could have given you.
- **Ask before destructive fallout.** If deleting the merged notes would break more than a couple of citations elsewhere (especially in `wiki/`), surface the concrete scope (which files, how many) and confirm the approach before deleting — don't assume.
- **A merge must not lose a tracked open item.** The sprint note is a *narrative* record; `open-items.md` is the *live* one, and they are not substitutes. Deleting a day note that solely owns a `[status::]` item drops it from the ledger with no error and no diff anyone reads. Re-home before you delete (step 4).
- **Only real work becomes an open item.** Routine housekeeping — merging your own stranded branches, gitignoring stray files, pulling a behind checkout — is not tracked work and must not be carried into the sprint note's open lists; it pollutes them and buries the items that matter. The daily briefings mix chores into their task lists, so filter when lifting from them. Companion to whatever scope rule [[vault-map]] sets for what becomes an open item at all.
- **Don't touch what's out of range.** Leave notes for dates/sprints outside the requested window untouched, even if adjacent.
- **Two audiences, one note.** Keep the stakeholder summary and the engineering detail both present and clearly separated by heading — don't merge them into one voice.
