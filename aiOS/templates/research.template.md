---
up: []
tags: [research]
related: []
author: ""
audience: ["mobile"]
created: {{date}}
updated: {{date}}
sources: []
aliases: []
---

# {{title}}

*Researched {{date}}.*

> [!tip] The short version
> The answer in four or five lines, for someone who reads nothing else. State the
> recommendation, not just the findings. If the answer is "it depends", say what on.

**The question.** One sentence, in the form it was actually asked.

**Constraints.** Anything that was fixed before the research started, quoted if a person
set it — a constraint discovered later invalidates work already done, so record when it
arrived.

---

## How to read this

**Audience.** Who this is for, and which sections are safe to hand over unchanged. If it
leaves the mobile team, every term they would not know belongs in the glossary.

**Owner.** Who to ask about any claim here.

### Method

*Delete the rows that do not apply — but do not delete the table.* A reader cannot weigh a
claim without knowing how it was obtained, and the strongest and weakest evidence in a note
usually look identical once written as prose.

| Kind | Weight | Where used |
|---|---|---|
| Repo / code inspection | **Strongest — the code is the final authority** | |
| Vendor's own page, fetched `<date>` | Strong for pricing and product limits | |
| Official platform documentation | Strong for what a platform does | |
| Measurement (BigQuery, logs) | Strong, but re-measure rather than cite a stale figure | |
| Third-party comparison / community report | **Weakest — flag every use inline** | |

**Where sources disagree, say so and leave it open.** Picking one silently is the failure
mode; a named contradiction is a finding.

### Personas affected

*Delete only if the subject genuinely touches no user.* One row per persona, **read from
its own note under `atlas/personas/`** rather than from a compiled summary or from this
document's own table. Every pass done this way has changed a design decision — a payload
field, a trigger, a security model — and the constraint is usually buried in a stated
frustration rather than in the part about the feature.

| Persona | What their work implies | Source read |
|---|---|---|
| | | |

Cite each persona note in `sources:`; `note-review.py` checks that you did.

### Revision history

*Only once the note has actually changed direction — delete this section otherwise.* A note
that reversed is more trustworthy than one that never did, but **only if the reversal is
visible.** Mark superseded sections in place; never quietly rewrite them.

| Rev | Change | Effect |
|---|---|---|
| 1 | | |

---

## Findings

What is true, organised so a reader can stop early. Lead each with the claim, not the
journey. Cite the load-bearing numbers inline — those are the ones that get challenged.

## Options

One subsection per option, each ending with the same two lines so they can be compared:

**Subscription:** new spend, or none — see the house rule that cost means vendor spend, not
developer time.
**Effort:** rough, and say which parts are not yours to estimate.

## Recommendation

Name one. A research note that lists options without recommending has moved the decision,
not helped it. Say what would change your mind.

## Limitations

*Never delete this section.* Gather every caveat here even if it also appears inline — a
reader who skims meets this section and nothing else.

| Limitation | Consequence |
|---|---|
| | |

Say plainly what you could **not** determine. "I could not establish X, and here is what I
ruled out" is a finding.

## Open

- [ ] One line per thing still to settle, each naming who can settle it. [status:: open] [raised:: {{date}}]

## Glossary

*Required when `audience:` extends beyond `mobile`; delete otherwise.*

| Term | Meaning |
|---|---|
| | |

> [!warning] Re-verify after `<date>`
> Give perishable findings an expiry. Vendor tiers and platform rules move; a figure with no
> date reads as current forever.

<!-- No References section. Entries live in `sources:` frontmatter and `pdf-builder` renders
     them as a numbered appendix — writing one here produces two headings with the same name
     and the same anchor in the PDF, and the contents then points at the wrong one. Keep each
     entry a locator plus a short label, and date anything that decays: a reference nobody
     can date is a reference nobody can re-check. -->
