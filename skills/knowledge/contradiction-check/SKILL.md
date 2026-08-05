---
name: contradiction-check
description: Find where the ideaVerse disagrees with itself or with the code — conflicting open-item statuses, deadline dates, stale frontmatter, and API fields claimed but absent from the swagger. Use after editing several notes, before relying on the vault, or on a 'check for contradictions' trigger.
---

# Contradiction Check

> **Paths** are relative to the **vault root** — the directory containing `aiOS/`, `ideaVerse/` and `wiki/` (commonly `docs/`). `<vault>` below stands for it. The scripts resolve their own locations, so a command works from any working directory.

Where the vault contradicts **itself** or the **code**. Complements `vault-health` (structure): this one is about notes that are all well-formed and present, but disagree.

## The script

```bash
python3 <vault>/aiOS/scripts/contradiction-check.py
python3 <vault>/aiOS/scripts/contradiction-check.py --json
python3 <vault>/aiOS/scripts/contradiction-check.py --only status,deadline
```

## The four detectors

| Detector | Severity | What it finds |
|---|---|---|
| `status` | critical | The same `[[open_item]]` carrying different `[status::]` in different notes, or a checkbox disagreeing with its own `[status::]` |
| `deadline` | critical | A prose date that disagrees with the `[due::]` for the same commitment, or one commitment with two different `[due::]` values |
| `stale` | warning | Frontmatter `updated:` ≥2 days behind the last commit that **modified** the file |
| `contract` | warning | A field attributed to a swagger schema that the schema doesn't declare — **heuristic** |

Each detector exists because this vault has actually suffered that failure:

- **`status`** — on 2026-07-28 the *"Finish the docking status UI"* item stayed `open` in the 07-23 day note after the work shipped in `a7318e203`. Two such conflicts had to be reconciled by hand.
- **`deadline`** — `2026-07-31` is restated as prose in 16 notes. One copy drifting is the realistic failure, not a `due::` typo.
- **`contract`** — the 07-28 note records correcting exactly this: the entity note claimed `dockCodes` and `externalOrderId`, neither of which exists in the spec.

## Tuning you must not undo

Three deliberate constraints keep this from becoming noise. Loosening any of them re-introduces a specific, measured failure:

1. **`stale` counts modifications only** (`git log --diff-filter=M`). This repo squash-merges — `a7318e203` *added* ~40 vault notes in one commit. Counting an add as "last touched" made 28 notes look stale when nothing had been edited; 94 of 123 notes have no modify-commit at all.
2. **`deadline` skips any line that already states the correct date.** Deadline summary lines legitimately name several dates ("security review 07-30 and the release 07-31"); flagging the other one produced 25 false positives, every single finding.
3. **`contract` skips tokens near negation markers** ("no such field", "Corrected", "absent from"). A note that *documents* a correction mentions the bad field name by necessity — that's the vault being right, not wrong.

## Explicitly not detected

Generic "do X" vs "don't do X" conflicting advice. A regex can't judge it. That's the analytical pass below.

## The analytical pass

After the script, check what it structurally cannot:

- **Decision reversals** — a decision recorded one way in a day note and another in a concept note. `wiki-sync` mines day notes into concepts, so a reversal leaves both versions alive.
- **Code vs note** — does an `efforts/works/` note still describe reality? The code is the final authority.
- **Superseded scope** — an item narrowed in practice but still worded broadly (the kind of thing that ages in `open-items.md` looking bigger than it is).

## Resolving findings

1. Fix it in the **owning note** — flip `[status::]`, correct the date. Keep the original text and append `→ superseded/resolved <date>: …` so the history survives.
2. Re-run `python3 <vault>/aiOS/scripts/open-items.py --today <today>` so the ledger clears.
3. **Never hand-edit `open-items.md`** — it's generated.

## When to use

- After editing several notes, especially day notes that carry items forward
- Before trusting the vault for a decision
- After a squash-merge brings a branch's notes in
- On "check for contradictions" or `/contradiction-check`

## Limitations

- `contract` is heuristic — the claim side is prose, so treat hits as "go look", not proof.
- `stale` can't see edits that were never committed.
- A `CLEAN` result means *these four detectors* found nothing, not that the vault is consistent. The detectors are verified to fire on synthetic conflicts, so clean is meaningful — but it is not the same as correct.
