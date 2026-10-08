#!/usr/bin/env python3
"""
note-review — review a single vault note for quality and completeness.

Checks:
  - Frontmatter completeness, per note flavour (standard notes need up/related/created;
    atlas/apis clippings need title/source/created)
  - Wikilink resolution against the WHOLE vault — a note linking the briefing or a
    compiled wiki note is correct even though neither lives under ideaVerse/
  - Structure: body substance, heading presence, single-purpose heading check
  - Source traceability: unsourced prescriptive or quantitative claims. The vault rule is
    "every figure / decision / deadline traces to a source", so a note asserting versions,
    counts, dates or obligations while `sources:` is empty is the thing worth flagging.

Usage:
  python3 aiOS/tools/ideaVerse/note-review.py <path-to-note.md>
  python3 aiOS/tools/ideaVerse/note-review.py --json <path-to-note.md>

Exit codes:
  0 — note passes (health excellent/good)
  1 — issues need attention
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

MIN_BODY_CHARS = 100

# Claim shapes that need a citation in this vault. Deliberately concrete: versions,
# ticket numbers, commit SHAs, counts, ISO dates and obligation language.
CLAIM_PATTERNS = {
    "version": re.compile(r"\bv?\d+\.\d+\.\d+\b"),
    "ticket": re.compile(r"\b(?:ticket|US|PR)\s*#?\d{4,6}\b", re.IGNORECASE),
    "commit": re.compile(r"\b[0-9a-f]{7,40}\b"),
    "date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "obligation": re.compile(r"\b(?:must|should|needs to|is required to)\b", re.IGNORECASE),
}


def check_frontmatter(note: dict) -> list[dict]:
    issues = []
    fm = note["frontmatter"]
    missing = V.required_fields_for(note) - set(fm.keys())
    if missing:
        kind = "clipping" if V.is_clipping(note) else "note"
        issues.append({
            "severity": "fatal",
            "message": f"{kind} missing required fields: {', '.join(sorted(missing))}",
        })
    if not fm.get("tags"):
        issues.append({"severity": "info", "message": "No tags defined — add topical tags"})
    return issues


def check_wikilinks(note: dict) -> list[dict]:
    known = V.resolvable_basenames()
    return [
        {"severity": "broken", "message": f"[[{t}]] not found anywhere in the vault"}
        for t in V.unresolved_targets(note, known)
    ]


def check_content_quality(note: dict) -> list[dict]:
    issues = []
    body = note["body"]
    headings = re.findall(r"^#{1,6}\s+(.+)$", body, re.MULTILINE)

    if len(body) < MIN_BODY_CHARS:
        issues.append({
            "severity": "empty",
            "message": f"Body too short ({len(body)} chars) — needs more substance",
        })

    for h in headings:
        if "—" in h or "–" in h:
            continue  # descriptive em-dash headings are the house style, not comparisons
        if re.search(r"\b(?:vs|versus|compared to|compared with)\b", h, re.IGNORECASE):
            issues.append({
                "severity": "suggestion",
                "message": f"Heading '{h}' compares two things — split if the topics are distinct",
            })

    # A raw clipping is one fenced dump by design — headings would be noise.
    if not headings and len(body) > MIN_BODY_CHARS and not V.is_clipping(note):
        issues.append({"severity": "suggestion", "message": "No headings — add structure"})
    return issues


# A research note is the kind most likely to be read by someone who cannot ask the
# author anything — a backend team, product, or the author themselves in six months.
# Two sections carry that weight and are the two reliably forgotten, because a note
# reads finished without them: how each finding was obtained, and what it cannot
# support. Presence is checkable here; whether they are honest is a review.
RESEARCH_DIR = "calendar/research/"
# Both accept the house phrasings, not one spelling. "What I could not determine" is
# what the researcher agent is told to write (runbook rule 7), and it predates this
# check — flagging notes that already do the right thing under a different heading
# would teach people to rename sections rather than write them.
RESEARCH_SECTIONS = {
    "Method": re.compile(
        r"^#{2,3}\s+.*\b(method|methodology|how (?:i|we) (?:checked|verified|tested|looked)"
        r"|evidence|approach)\b",
        re.IGNORECASE | re.MULTILINE),
    "Limitations": re.compile(
        r"^#{2,3}\s+.*\b(limitation|caveat|could ?n[o']?t determine|what (?:i|we) "
        r"(?:could not|couldn't) |unknowns|threats to validity)",
        re.IGNORECASE | re.MULTILINE),
}


# A note written for readers outside the team is a deliverable, and a deliverable
# should not contain the record of its own making. Four kinds of that slipped into
# one research note before a human objected to each in turn: edit history
# ("correcting an earlier judgement"), governance ("Decision 2026-10-01 — ruled out
# of scope by X"), review process ("pass 1 recommended"), and a checkbox task list.
# Each is grep-able, which is the only reason this check can exist.
PROCESS_VOICE = {
    'edit history': re.compile(
        r'\b(?:an?|the) (?:earlier|previous|first|later) (?:revision|draft|pass|version)\b'
        r'|\bcorrect(?:ing|ed) an earlier\b|\bthis note (?:said|claimed|previously)\b'
        r'|\bsupersede[ds]?\b|\bwas wrong\b|\bon a second look\b', re.IGNORECASE),
    'governance': re.compile(
        r'^>?\s*\[?!?\w*\]?\s*Decision \d{4}-\d{2}-\d{2}|\bruled (?:it )?out of scope\b'
        r"|\b\w+'s call\b", re.IGNORECASE | re.MULTILINE),
    'review process': re.compile(r'\bpass [1-9]\b|\breview pass(?:es)?\b', re.IGNORECASE),
    # A tracked open item is not a todo list: `[status:: …]` is the vault's own
    # convention, it compiles into the open-items ledger, and the research template
    # prescribes it. Only an untracked checkbox is the thing worth flagging.
    'a task list': re.compile(r'^\s*- \[[ x]\] (?![^\n]*\[status::)', re.MULTILINE),
}

# A note that names a persona should have read that persona's own note. Every time
# this was done by hand it changed the design — a payload field, a trigger, a
# security model — and every time it was skipped the summary was trusted instead.
PERSONA_DIR = 'atlas/personas/'


def audience_of(note: dict) -> list[str]:
    raw = note['frontmatter'].get('audience') or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(a).strip().strip('"\'[]') for a in raw if str(a).strip()]


def check_process_voice(note: dict) -> list[dict]:
    """Flag the document narrating its own making — only where it will be read outside."""
    audience = [a for a in audience_of(note) if a and a != 'mobile']
    if not audience:
        return []
    hits = sorted(kind for kind, rx in PROCESS_VOICE.items() if rx.search(note['body']))
    if not hits:
        return []
    return [{
        'severity': 'suggestion',
        'message': (f"Reads as {', '.join(hits)} — this note declares audience "
                    f"{', '.join(audience)}. State the finding, not how the document "
                    f"reached it; decisions belong in the owning note and tasks on the board"),
    }]


def known_personas() -> set[str]:
    """Basenames under `atlas/personas/`. Resolved from disk rather than matched by
    shape, so a document that merely looks persona-shaped — `driver-device-fleet` is
    a measurement note, not a persona — is not mistaken for one."""
    folder = V.IDEAVERSE_DIR / 'atlas' / 'personas'
    return {p.stem for p in folder.glob('*.md')} if folder.is_dir() else set()


def check_persona_sources(note: dict) -> list[dict]:
    """A note that names personas should cite their source notes, not a summary of them."""
    personas = known_personas()
    if not personas:
        return []
    # A persona note naming its siblings, and the hub that indexes them, are not
    # reasoning from a summary — they are the sources. Measured at 13 false
    # positives in 16 before these exemptions.
    if note['path'].startswith('atlas/personas/'):
        return []
    body = note['body']
    # A `[[wikilink]]` is a citation. Only an unlinked mention suggests the author
    # worked from a compiled summary rather than the persona's own note.
    named = sorted(p for p in personas
                   if re.search(rf'\b{re.escape(p)}\b', body)
                   and not re.search(rf'\[\[{re.escape(p)}(?:\|[^\]]*)?\]\]', body))
    if not named:
        return []
    fm = note['frontmatter']
    # Matched as whole link targets, not as substrings: `[[guest-driver-persona-check]]`
    # in `related:` contains "guest-driver" and was exempting notes that never
    # discuss the persona.
    cited = {re.sub(r'^\[\[|\]\]$|\|.*$', '', str(x).strip())
             for x in (fm.get('sources') or []) + (fm.get('related') or [])}
    cited |= {Path(str(x)).stem for x in (fm.get('sources') or [])}
    missing = [n for n in named if n not in cited]
    if not missing:
        return []
    return [{
        'severity': 'suggestion',
        'message': (f"Names {', '.join(missing)} but does not cite "
                    f"{'their' if len(missing) > 1 else 'its'} persona note in `sources:` — "
                    f"read `atlas/personas/` rather than a compiled summary; "
                    f"every such pass so far changed a design decision"),
    }]


def check_research_structure(note: dict) -> list[dict]:
    """Research notes carry Method and Limitations; other folders are unaffected."""
    if not note["path"].startswith(RESEARCH_DIR):
        return []
    body = note["body"]
    # Too short to have sections yet — `check_content_quality` already says so, and
    # repeating it here would just double the noise on a stub.
    if len(body) < MIN_BODY_CHARS:
        return []
    missing = [name for name, rx in RESEARCH_SECTIONS.items() if not rx.search(body)]
    if not missing:
        return []
    return [{
        "severity": "suggestion",
        "message": (
            f"Research note has no {' or '.join(missing)} section — "
            f"a reader who cannot ask you anything needs how you know, and what this "
            f"cannot support. See aiOS/templates/research.template.md"
        ),
    }]


def check_sources(note: dict) -> list[dict]:
    """Flag concrete claims made in a note that cites nothing.

    Replaces an inherited check that scanned for currency amounts and then discarded the
    result without reporting anything — it could never fire.
    """
    fm = note["frontmatter"]
    # Clippings cite their origin in `source:` (singular) — that IS their traceability.
    if fm.get("sources") or (V.is_clipping(note) and fm.get("source")):
        return []
    body = note["body"]
    kinds = sorted(k for k, rx in CLAIM_PATTERNS.items() if rx.search(body))
    if not kinds:
        return []
    return [{
        "severity": "suggestion",
        "message": (
            f"Asserts {', '.join(kinds)} but `sources:` is empty — "
            f"every figure/decision/deadline should trace to a source"
        ),
    }]


def review_note(path: Path) -> dict:
    if not path.exists():
        return {"error": f"File not found: {path}"}

    abs_path = path.resolve()
    text = abs_path.read_text(encoding="utf-8")
    fm, body = V.parse_frontmatter(text)
    try:
        rel = abs_path.relative_to(V.IDEAVERSE_DIR).as_posix()
    except ValueError:
        rel = abs_path.name
    note = {
        "path": rel, "abspath": abs_path, "basename": abs_path.stem,
        "frontmatter": fm, "body": body.strip(),
    }

    issues: list[dict] = []
    issues += check_frontmatter(note)
    issues += check_wikilinks(note)
    issues += check_content_quality(note)
    issues += check_research_structure(note)
    issues += check_process_voice(note)
    issues += check_persona_sources(note)
    issues += check_sources(note)

    weights = {"fatal": 10, "broken": 8, "empty": 6, "suggestion": 1, "info": 0}
    total = sum(weights.get(i["severity"], 0) for i in issues)
    health = (
        "excellent" if total == 0 else
        "good" if total <= 2 else
        "needs work" if total <= 6 else
        "poor"
    )
    return {"path": rel, "health": health, "issues_count": len(issues), "issues": issues}


def format_review(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['error']}"
    lines = [f"Note: {r['path']}", f"Health: {r['health'].upper()}", f"Issues: {r['issues_count']}", ""]
    if not r["issues"]:
        lines.append("✓ No issues found!")
        return "\n".join(lines)
    lines.append("Issues:")
    icons = {"fatal": "🔴", "broken": "🟠", "empty": "🟡", "suggestion": "🔵", "info": "⚪"}
    for i in r["issues"]:
        lines.append(f"  {icons.get(i['severity'], '⚪')} [{i['severity']}] {i['message']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Review a vault note for quality.")
    ap.add_argument("path", type=Path, help="Path to the .md file to review")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    result = review_note(args.path)
    print(json.dumps(result, indent=2) if args.json else format_review(result))

    if "error" in result:
        return 1
    return 0 if result["health"] in ("excellent", "good") else 1


if __name__ == "__main__":
    raise SystemExit(main())
