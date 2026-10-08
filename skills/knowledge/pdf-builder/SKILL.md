---
name: "pdf-builder"
description: "Generate a PDF from a vault markdown note with one command, paginated properly — headings never stranded at the foot of a page, tables never split with a lone row, mermaid diagrams rendered. Use whenever a note needs to become a PDF to send to someone (sprint notes, security documents, handoff briefs, UAT findings), or when a generated PDF paginates badly."
metadata:
  last_modified: "Sun, 17 Aug 2026 00:00:00 GMT"
---

# PDF Builder

Renders a markdown note straight to PDF. **Obsidian is not involved** — the pipeline is markdown → HTML (python-markdown) → headless Chrome `--print-to-pdf`.

```bash
python3 .claude/skills/pdf-builder/md2pdf.py "docs/ideaVerse/calendar/sprints/2026 sprint 3.md"
#   docs/ideaVerse/calendar/sprints/2026 sprint 3.pdf
#   13 pages · 444 KB · 2 diagram(s)
```

| Flag | |
|---|---|
| `-o out.pdf` | output path (default: next to the source, same stem) |
| `--no-toc` | skip the contents list |
| `--no-references` | skip the References appendix built from `sources:` |
| `--strict` | exit non-zero if the render contains a blank page |
| `--no-mermaid` | skip diagram rendering; diagram source is boxed instead |
| `--keep-html` | leave the intermediate `.build.html` for inspection |

## What it handles

The vault's Obsidian dialect, all of which would otherwise leak into the PDF as raw text:

- **YAML frontmatter** — stripped. It would otherwise print as a wall of metadata on page 1. A `title:` field, if present, becomes the document title.
- **`[[wikilinks]]`** — flattened to their text (`[[a|b]]` → `b`). A PDF reader cannot follow them, so brackets are just noise.
- **`> [!warning]` callouts** — converted to styled boxes, colour-coded by kind, kept whole across page breaks.
- **References** — the note's `sources:` frontmatter, rendered as a numbered appendix with URLs linked. **This exists because frontmatter is stripped**, so before it a note ending `**Sources:** see frontmatter` pointed the reader at something the renderer had removed, and a document handed outside the team carried no citations at all. Both YAML shapes are read: inline `sources: ["a", "b"]` and the block list. An entry that is not a URL still renders.
- **Contents** — a list of `##` headings, inserted after the `<h1>` for notes past `TOC_MIN_HEADINGS` (6). Below that it is noise. Only level 2; deeper nesting makes a 20-page note unreadable.

  > **`toc_tokens` is a tree, not a list.** With an `# H1` present — which every vault note has — the `##` headings arrive as its *children*, so a flat scan for level 2 finds nothing and the contents list silently renders as empty. `flatten_toc` walks it depth-first; a regression test builds the nested shape explicitly. The References appendix worked while this was broken, so eyeballing one output would have passed it.
- **` ```mermaid ` fences** — rendered as real diagrams via a cached mermaid bundle.
- **`<div style="break-after: page;">`** — preserved, so the hard breaks authors place still work.
- **`{: .new-page }` on a heading** — `attr_list` is enabled, so `## Glossary {: .new-page }` starts a page. **Prefer this to an empty `<div class="page-break">`.** An empty block carrying `break-after` becomes a page of its own whenever it lands at the top of a fresh one, which is how a blank page 24 reached a document that had already been sent. `break-before` on the element that should lead the page cannot do that.
- **`h2#references`** — the generated citations always start a page.

## Every render is audited

After printing, the page tree is walked **in reading order** and each page's content stream decoded, so a page carrying no glyphs is reported:

```
  ! blank page(s): 24 — almost always an empty block carrying `break-after: page`
  · very light page(s): 3 (26 glyph runs)
```

**A blank page is indistinguishable from a real one by page count**, which is how one reached a document that had already been sent. Light pages are reported but never fail — a cover page is legitimately light. `--strict` exits 1 on a blank one, for a hook or a release step.

Alongside it a **structural audit** reports what renders fine but reads wrong:

- a **skipped heading level** — `##` then `####` is how a nine-part section collapsed to one contents line;
- **two headings reading the same** — their ids differ (`references`, `references_1`), so the damage is identical contents rows and a hand-written `#references` link reaching the first;
- **the contents pointing twice at one anchor**, or at no heading at all — the defect the audit was written after.

`--strict` keys on **blank pages only**; structural problems are reported and do not fail.

Page objects are **not** stored in page order, so the audit follows `/Kids`. Numbering the objects instead names the wrong page, and a test fixture with deliberately reversed object numbers holds that.

## The pagination rules — and which of them Chromium actually honours

In `pdf.css`. Both guarantees were **measured against headless Chrome on 2026-08-17**, because the obvious CSS for one of them silently does nothing:

**A heading never ends a page.** The intuitive rule — `break-after: avoid` on the heading — **does not work in Chromium**. Across 54 fixture configurations it never once changed where a heading landed; Chromium implements `break-inside: avoid` but effectively ignores `break-before/after: avoid`. What ships instead: each heading gets an `::after` that reserves `--pdf-heading-reserve` (5em) of space, cancelled by an equal negative margin so nothing shifts visually. That makes the heading's *box* tall, and `break-inside: avoid` is honoured — so a heading whose reserved block will not fit moves whole to the next page, carrying about four lines of its section with it. Verified: the tipping point moved 30 → 28 lines versus an unstyled control.

> Do not "simplify" that back to `break-after: avoid`. It reads as correct and silently regresses.

**A table is never split with a stranded row.** `break-inside: avoid` on the table, which Chromium *does* honour — a fixture whose table straddled the boundary went 2 → 3 pages with the rule on, i.e. the table moved whole rather than tearing. `tr { break-inside: avoid }` additionally guarantees no row is ever cut through the middle.

Alongside them: `orphans: 3 / widows: 3`, and `break-inside: avoid` on code blocks, callouts, images and diagrams.

**Tune `--pdf-heading-reserve` in `pdf.css`** if 5em is wrong for a document — larger keeps more of the section with its heading, at the cost of more whitespace at page feet.

## Limits worth knowing

- **A table taller than a page cannot be kept whole.** `break-inside: avoid` is best-effort; Chromium breaks it anyway. `thead` is set to repeat so the continuation keeps its column headers — but put a hard break before a long table so it starts at the top of a page and breaks once.
- **Hard breaks are still the author's judgement.** The CSS fixes local widows and orphans; it does not know that a section is a logical unit. A break before every `##` produces half-empty pages — break where a reader would want to turn.
- **Wide tables are clipped, not wrapped.** A table wider than the text column loses its right-hand edge. Shorten headers or split it.

## Requirements

- **Chrome, Chromium or Edge** — found automatically; edit `CHROME_CANDIDATES` in `md2pdf.py` for an unusual location.
- **python-markdown** — `pip3 install --user markdown`.
- **mermaid** — fetched once from jsdelivr and cached at `.claude/skills/pdf-builder/.mermaid.min.js` (gitignored, 3.3 MB). Offline with no cache, diagrams degrade to boxed source and the script says so rather than silently dropping them.

## Tests

37 tests in `tests/`, stdlib `unittest`, **no network, no Chrome, no PDF written** — they cover the text pipeline, which is where the failures are invisible until someone opens the file.

```bash
python3 -m unittest discover -s .claude/skills/pdf-builder/tests
```

The suite ships **with** the skill, so a consumer can verify its own copy after an upgrade rather than trusting that a renderer change landed cleanly. It touches no network, launches no Chrome and writes no PDF: every impure step is stubbed. A repo that discovers test directories automatically picks it up with no further wiring.

What they pin down: frontmatter never reaching the page, `[[wikilinks]]` leaving no brackets behind, callouts surviving Obsidian's spacing and fold markers with their titles HTML-escaped, mermaid fences extracted in order while other code fences are left alone, author page-breaks preserved, the stylesheet inlined so the output is self-contained, and — the two that matter operationally — that the mermaid cache is used **without touching the network**, and that being offline degrades to visible diagram source rather than raising or silently dropping the diagram.

## Committed PDFs go stale

Prefer generating a PDF and sending it to committing it. Where one *is* committed beside its `.md`, nothing detects the two drifting apart, so **re-run this and commit both after editing the note** — otherwise the version people read is the old one. A stale committed PDF is the failure mode here, and it is silent: the note looks maintained, and the artefact everyone outside the team actually opens is months behind.
