#!/usr/bin/env python3
"""
research-capture — validate and place a new note before it enters the ideaVerse.

Three subcommands:

  check <path>    Is this note ready to capture? Frontmatter for its flavour, resolvable
                  wikilinks (across the whole vault), unique basename, real body.
  suggest <text>  Which vault folder does this content belong in? Scores the vault
                  taxonomy (atlas/concepts, atlas/apis, efforts/works, calendar/..., …).
  exists <term>   Is this already documented? Matches basename, first heading and aliases
                  so a new note doesn't duplicate an existing concept.

Usage:
  python3 <vault>/aiOS/scripts/research-capture.py check ideaVerse/atlas/concepts/foo.md
  python3 <vault>/aiOS/scripts/research-capture.py suggest "the retry budget is three attempts"
  python3 <vault>/aiOS/scripts/research-capture.py exists "retry budget"

Exit codes:
  0 — ready / suggestion produced
  1 — issues found that need resolution
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

MIN_BODY_CHARS = 50
DATE_BASENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The vault's real taxonomy. Keys are folders under ideaVerse/; values are the
# vocabulary that signals a note belongs there.
TAXONOMY: dict[str, list[str]] = {
    "atlas/concepts": [
        "concept", "definition", "terminology", "glossary", "what is", "ubiquitous",
        "enum", "status", "state", "taxonomy", "axis", "pattern", "means",
    ],
    "atlas/documents": [
        "guide", "how-to", "how to", "setup", "onboarding", "architecture", "deploy",
        "build", "convention", "runbook", "structure",
    ],
    "atlas/apis": [
        "swagger", "openapi", "endpoint", "payload", "contract", "viewmodel",
        "schema", "request", "response", "curl",
    ],
    "atlas/personas": ["persona", "user type", "actor", "role", "operator"],
    "efforts/projects": [
        "project", "client", "customer", "rollout", "go-live", "milestone",
    ],
    "efforts/works": [
        "epic", "work in progress", "wip", "migration", "refactor", "feature",
        "implementation", "phase",
    ],
    "calendar/meetings": ["meeting", "uat", "kick-off", "kickoff", "call", "attendees", "agenda"],
    "calendar/research": ["research", "investigation", "spike", "findings", "comparison"],
    "calendar/releases": ["release", "version", "store", "changelog", "rollout notes"],
    "calendar/sprints": ["sprint", "velocity", "backlog", "retro"],
    "calendar/days": ["day note", "today", "daily log"],
}

# Domain vocabulary is per project, so it is configured rather than shipped: the entries
# in `captureKeywords` EXTEND the framework taxonomy above instead of replacing it, so a
# vault gains its own terms without forking this file.
for _folder, _words in V.CONFIG["captureKeywords"].items():
    TAXONOMY.setdefault(_folder, []).extend(str(w) for w in _words)


# ── check ──────────────────────────────────────────────────────

def _date_pair_exempt(abs_path: Path, others: list[Path]) -> bool:
    """One note per calendar subfolder per date is by design, not a duplicate.

    Mirrors `vault-lint.check_duplicate_basenames`: a date names both a
    calendar/days/ note and a calendar/briefings/ note, and the vault links them
    path-style ([[briefings/2026-07-23]]). Without this the two tools disagree and
    every day note reports one permanent false positive.
    """
    if not DATE_BASENAME_RE.match(abs_path.stem):
        return False
    try:
        paths = [abs_path.relative_to(V.IDEAVERSE_DIR).as_posix()] + [
            p.relative_to(V.IDEAVERSE_DIR).as_posix() for p in others
        ]
    except ValueError:
        return False  # checking a file outside the vault — no exemption applies
    folders = {p.rsplit("/", 1)[0] for p in paths}
    return len(folders) == len(paths) and all(f.startswith("calendar/") for f in folders)


def check_note_ready(note_path: Path) -> list[str]:
    if not note_path.exists():
        return [f"[FATAL] File not found: {note_path}"]

    abs_path = note_path.resolve()
    fm, body = V.parse_frontmatter(abs_path.read_text(encoding="utf-8"))
    note = {
        "path": abs_path.name, "abspath": abs_path, "basename": abs_path.stem,
        "frontmatter": fm, "body": body.strip(),
    }
    issues: list[str] = []

    missing = V.required_fields_for(note) - set(fm.keys())
    if missing:
        kind = "clipping" if V.is_clipping(note) else "note"
        issues.append(f"[FATAL] {kind} missing required frontmatter: {', '.join(sorted(missing))}")

    # Duplicate basename: any OTHER vault note already using this stem.
    others = [
        p for p in V.IDEAVERSE_DIR.rglob("*.md")
        if p.stem == abs_path.stem and p.resolve() != abs_path
    ]
    if others and not _date_pair_exempt(abs_path, others):
        where = ", ".join(p.relative_to(V.IDEAVERSE_DIR).as_posix() for p in others)
        issues.append(f"[DUPE] Basename '{abs_path.stem}' already used by: {where}")

    for t in V.unresolved_targets(note, V.resolvable_basenames()):
        issues.append(f"[BROKEN] Wikilink [[{t}]] resolves to nothing in the vault")

    if len(note["body"]) < MIN_BODY_CHARS:
        issues.append(f"[EMPTY] Body has only {len(note['body'])} chars — too short to be useful")

    return issues


# ── suggest ────────────────────────────────────────────────────

def suggest_location(text: str) -> dict[str, int]:
    low = text.lower()
    scores = {
        folder: sum(1 for kw in kws if kw in low)
        for folder, kws in TAXONOMY.items()
    }
    scores = {k: v for k, v in scores.items() if v > 0}
    if not scores:
        # No signal — concepts is the vault's default home for a new idea.
        scores["atlas/concepts"] = 1
    return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))


# ── exists ─────────────────────────────────────────────────────

def check_existing_term(term: str) -> list[str]:
    results = []
    low = term.lower()
    for note in V.load_notes():
        rel = note["path"]
        if note["basename"].lower() == low:
            results.append(f"{rel} (basename match)")
        m = re.search(r"^#\s+(.+)$", note["body"], re.MULTILINE)
        if m and low in m.group(1).lower():
            results.append(f"{rel} (title match: '{m.group(1).strip()}')")
        aliases = note["frontmatter"].get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            if alias and low in str(alias).lower():
                results.append(f"{rel} (alias match: '{alias}')")
    return results


# ── Main ───────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Validate and place a note before capture.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Check whether a note is ready to capture")
    p_check.add_argument("path", type=Path, help="Path to the .md file")

    p_sug = sub.add_parser("suggest", help="Suggest a vault folder for unfiled text")
    p_sug.add_argument("text", type=str, help="Content to analyse")

    p_ex = sub.add_parser("exists", help="Check whether a term is already documented")
    p_ex.add_argument("term", type=str, help="Term to search for")

    args = ap.parse_args()

    if args.command == "check":
        issues = check_note_ready(args.path)
        if issues:
            print(f"❌ {args.path.name} is NOT ready to capture:\n")
            for i in issues:
                print(f"  {i}")
            return 1
        print(f"✓ {args.path.name} is ready to capture!")
        return 0

    if args.command == "suggest":
        print("Suggested vault locations:\n")
        for loc, score in suggest_location(args.text).items():
            print(f"  {loc}/ (score: {score})")
        return 0

    results = check_existing_term(args.term)
    if results:
        print(f"Found {len(results)} match(es) for '{args.term}':\n")
        for r in results:
            print(f"  - {r}")
    else:
        print(f"No existing notes found for '{args.term}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
