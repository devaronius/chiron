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
  python3 <vault>/aiOS/scripts/note-review.py <path-to-note.md>
  python3 <vault>/aiOS/scripts/note-review.py --json <path-to-note.md>

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
