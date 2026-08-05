---
name: domain-modeling
description: Build and sharpen a project's ideaVerse. Use when the user wants to pin down domain terminology or a ubiquitous language, record an architectural decision, or when another skill needs to maintain the ideaVerse.
---

# IdeaVerse Modeling

> **Paths** are relative to the **vault root** — the directory containing `aiOS/`, `ideaVerse/` and `wiki/` (commonly `docs/`). `<vault>` below stands for it. The scripts resolve their own locations, so a command works from any working directory.

Actively build and sharpen the project wiki as you design. This is the *active* discipline — challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* the wiki for vocabulary is not this skill — that's a one-line habit any skill can do. This skill is for when you're changing the IdeaVerse, not just consuming it.)

**Where things land** (the source of truth is `ideaVerse/`, never `wiki/` — that's compiled output):

- **A domain term / ubiquitous-language concept** → a concept note at `ideaVerse/atlas/concepts/<concept>.md`, one note per concept, built from the [concept template](../../../<vault>/aiOS/templates/concept.template.md). A concept note may define several tightly-related sub-terms via `**bold lead-ins**` and its `aliases:` frontmatter (don't shatter a cohesive concept into one-note-per-tiny-term).
- **A decision** → *no separate ADR folder.* If it's durable and about a concept, put a **Decision block** in that concept note. If it's point-in-time and project-scoped, put it in the driving effort note (`ideaVerse/efforts/works/<work>.md`). Ask yourself: "is this about a concept, or about an effort?"
- **A backend API contract** → two paired artifacts: a raw Swagger clipping at `ideaVerse/atlas/apis/<name>_api.md` and a compiled entity note at `wiki/entities/<name>-api.md` that indexes it. Follow the [API note template](../../../<vault>/aiOS/templates/api-note.template.md).

> Concept-shaped docs may still live in `atlas/documents/` (mid-migration) or fan out into a hub doc there. So **search both `atlas/concepts/` and `atlas/documents/`** before deciding a term is undocumented.

## Before you write or challenge: look it up

`wiki-sync` keys sources by basename, so a concept note's basename must be **unique across the whole vault**. And you can only challenge or extend the glossary if you've actually loaded it. So, before creating a concept note or contradicting a term:

1. Scan `wiki/wiki.catalog.jsonl` — match the term against each row's `id` / `title` / `desc` / `aliases`.
2. Grep the source `aliases:` frontmatter (the catalog's aliases may be backfilled lazily, so go to source too):
   ```bash
   grep -rin "aliasyouareabout" ideaVerse/atlas/concepts ideaVerse/atlas/documents
   ```
3. **If it already exists, update or challenge that note — never create a duplicate.** If it doesn't, create a new concept note from the template.

## During the session

### Challenge against the glossary
When the user uses a term that conflicts with the existing language in the wiki, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language
When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things." Capture the winner as the concept's title; capture the rejected/alternate spellings as `aliases:` so the next lookup finds it.

### Discuss concrete scenarios
When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts. What survives becomes the **"Not to be confused with"** section.

### Cross-reference with code
When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?" If it can't be resolved on the spot, record it in the concept note's **open-questions `>` callout** — the code is the final authority.

### Update IdeaVerse inline
When a term or decision resolves, write it into the right note **right there** — don't batch. Use the [concept template](../../../<vault>/aiOS/templates/concept.template.md); its required-when-applicable sections ("Not to be confused with", open-questions callout) are the sharpening — don't drop them when they apply. Fill `sources:` (code paths, Teams/URLs) so the compiled wiki stays traceable.

## Closing a completed effort

When an `efforts/works/<work>.md` finishes, redistribute its knowledge so the durable facts live where readers look and the log becomes history:

1. **Migrate the end-state into the concept/entity notes.** The durable "how it works now" belongs in the `concept`/`entity` note (rewrite the stale parts to the shipped reality); the effort note keeps the *journey* — including the dead-ends and reversals, which are the lessons. Add a durable **Decision block** to the concept for any architectural choice that outlives the effort.
2. **Mark the effort's status** (e.g. `✅ COMPLETE & verified (<date>)`) at the top and point to the concept/entity note as the source of truth. Keep the superseded sections below, clearly tagged as history — don't delete the reasoning.
3. **Promote surviving follow-ups to real trackers.** Genuine forward work (deferred phases, pending verification, rollout) belongs in an owning note that outlives the effort — a `project` note like [[mobile_ops]] for standing items, or the concept. Don't leave live work buried in a note you're marking Done. When this means creating or closing open items, follow the [[open_item]] conventions (see the day-note runbook) — don't reinvent the schema here.

## At the end of the session
Call the `wiki-sync` skill to compile your new/changed `ideaVerse/` sources into `wiki/` and update the catalog.
