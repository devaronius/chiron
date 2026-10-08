#!/usr/bin/env python3
"""
vault-lint — ideaVerse structural health check & lint.

Runs structural checks over ideaVerse/ and reports issues:
  [FATAL]   — missing required frontmatter fields (note is malformed)
  [BROKEN]  — wikilink [[target]] resolves to nothing anywhere in the vault
  [ORPHAN]  — note is not referenced by any other note (and isn't a root note)
  [EMPTY]   — note has only frontmatter, no substantive body content
  [DUPE]    — two notes share the same basename (basename must be unique)
  [INBOX-LINK] — a filed note links to a note still in the `+/` inbox
  [DOC-KIND] — an atlas/documents/ note has no allowed `kind:` (see vault-map)
  [CONCEPT-KIND] — an atlas/concepts/ note is not `kind: domain` or `kind: behaviour`
  [STALE]   — wiki is out of sync with the vault (delegates to wiki-sync)
  [INFO]    — informational: notes with no sources cited; shipped efforts due for a
              stub (RETIRE)

Two things this checks that a naive linter gets wrong:

  * Wikilinks resolve across the WHOLE vault, not just ideaVerse. The briefing note
    sits at the vault root; a compiled note lives in wiki/; `[[vault-map]]` is an aiOS
    map. Resolving against ideaVerse alone reported 61 broken links of which only ~14
    were real.
  * Required frontmatter is per note flavour. Raw API clippings under atlas/apis/
    carry title/source/created, not up/related/created.

Usage:
  python3 aiOS/tools/ideaVerse/vault-lint.py              # full report (exit 1 if issues)
  python3 aiOS/tools/ideaVerse/vault-lint.py --quiet      # summary line only
  python3 aiOS/tools/ideaVerse/vault-lint.py --fix        # auto-fix what's fixable
  python3 aiOS/tools/ideaVerse/vault-lint.py --categories # print category coverage table

Auto-fix (--fix) handles adding a missing 'created' date to an otherwise well-formed
note. Everything else needs human judgment.

Exit codes:
  0 — no issues found
  1 — issues found, or error
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402


# ── Checks ─────────────────────────────────────────────────────

def check_required_fields(notes: list[dict]) -> list[str]:
    """Notes missing the frontmatter fields their flavour requires."""
    issues = []
    for n in notes:
        missing = V.required_fields_for(n) - set(n["frontmatter"].keys())
        if missing:
            kind = "clipping" if V.is_clipping(n) else "note"
            issues.append(
                f"[FATAL] {n['path']}: {kind} missing required fields: {', '.join(sorted(missing))}"
            )
    return issues


def check_broken_wikilinks(notes: list[dict]) -> list[str]:
    """Wikilinks resolving to nothing, grouped by TARGET rather than by source note.

    One absent note is one problem, not N. Reporting per-source turned four missing week
    notes into 19 lines and buried the fact that the fix is "write four notes".
    """
    known = V.resolvable_basenames()
    by_target: dict[str, list[str]] = {}
    for n in notes:
        for t in V.unresolved_targets(n, known):
            by_target.setdefault(t, []).append(n["path"])

    issues = []
    for target, sources in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        shown = ", ".join(sorted(sources)[:4])
        more = f" (+{len(sources) - 4} more)" if len(sources) > 4 else ""
        issues.append(
            f"[BROKEN] [[{target}]] does not exist — linked from {len(sources)} note(s): {shown}{more}"
        )
    return issues


def check_orphans(notes: list[dict]) -> list[str]:
    """Notes no other note points at (excluding declared entry points)."""
    referenced: set[str] = set()
    for n in notes:
        referenced |= {t.split("/")[-1] for t in V.link_targets(n)}
        # Plain (non-wikilink) string references in up/related still count.
        for field in ("up", "related"):
            val = n["frontmatter"].get(field, [])
            if isinstance(val, str):
                val = [val]
            for item in val:
                s = str(item).strip()
                if s and "[[" not in s:
                    referenced.add(s)

    issues = []
    for n in notes:
        bn = n["basename"]
        if bn in V.ROOT_NOTES:
            continue
        # Chronological records are reached by DATE, not by inbound link — a day note or
        # briefing nobody links to is normal. Their real index is the sprint note they
        # link as parent, and coverage-gap reports a missing one via sprint-note-missing;
        # double-reporting it here as N orphans hides the single root cause.
        if DATE_BASENAME_RE.match(bn) and n["path"].startswith("calendar/"):
            continue
        # A raw clipping is a SOURCE document. Its consumer is the compiled wiki note
        # that cites it, not an inbound vault wikilink — every clipping in this vault is
        # cited by a wiki note while none is linked from another ideaVerse note. Whether
        # a clipping was ever compiled is wiki-sync's UNCOVERED bucket, not ours.
        if V.is_clipping(n):
            continue
        # A note referenced only by itself is still an orphan.
        others = referenced - {bn} if bn not in referenced else referenced
        if bn not in others:
            issues.append(f"[ORPHAN] {n['path']}: not referenced by any other note")
    return issues


INBOX_PREFIX = "+/"


def check_inbox_links(notes: list[dict]) -> list[str]:
    """Filed notes linking to a note that is still in the `+/` inbox.

    The inbox holds unfiled capture that moves out when processed, so a filed note
    depending on one depends on something about to move. Grouped by target like
    [BROKEN]: filing one inbox note fixes every link to it. Found when a bulk import
    left thirteen notes in `+/` and six of them were already linked from filed notes.
    """
    inbox = {n["basename"]: n["path"] for n in notes if n["path"].startswith(INBOX_PREFIX)}
    by_target: dict[str, list[str]] = {}
    for n in notes:
        if n["path"].startswith(INBOX_PREFIX):
            continue
        for t in V.link_targets(n):
            tail = t.split("|")[0].split("#")[0].split("/")[-1].strip()
            if tail in inbox:
                by_target.setdefault(tail, []).append(n["path"])

    issues = []
    for target, sources in sorted(by_target.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        unique = sorted(set(sources))
        shown = ", ".join(unique[:4])
        more = f" (+{len(unique) - 4} more)" if len(unique) > 4 else ""
        issues.append(
            f"[INBOX-LINK] [[{target}]] is still in the inbox ({inbox[target]}) — file it; "
            f"linked from {len(unique)} filed note(s): {shown}{more}"
        )
    return issues


def check_note_kinds(notes: list[dict]) -> list[str]:
    """Notes in a kinded folder (documents, concepts) whose `kind:` is missing or unknown."""
    issues = []
    for n in notes:
        problem = V.kind_issue(n, n["path"])
        if problem:
            tag, reason = problem
            issues.append(f"[{tag}] {n['path']}: {reason}")
    return issues


def check_empty_notes(notes: list[dict]) -> list[str]:
    return [
        f"[EMPTY] {n['path']}: only {len(n['body'])} chars of body content"
        for n in notes
        if len(n["body"]) < V.MIN_BODY_CHARS
    ]


DATE_BASENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_duplicate_basenames(notes: list[dict]) -> list[str]:
    """Basenames used more than once.

    Exempts the vault's deliberate one-per-date-per-kind shape: a date may name both a
    calendar/days/ note and a calendar/briefings/ note. That collision is structural, and
    the vault already works around it by linking path-style ([[briefings/2026-07-23]]).
    Flagging it would add one permanent false positive per date.
    """
    by_name: Counter = Counter(n["basename"] for n in notes)
    issues = []
    for name, count in by_name.most_common():
        if count <= 1:
            continue
        paths = [n["path"] for n in notes if n["basename"] == name]
        if DATE_BASENAME_RE.match(name):
            folders = {p.rsplit("/", 1)[0] for p in paths}
            # One note per calendar subfolder is by design; two in the same one is not.
            if len(folders) == len(paths) and all(f.startswith("calendar/") for f in folders):
                continue
        issues.append(f"[DUPE] basename '{name}' used {count} times: {' | '.join(paths)}")
    return issues


def check_wiki_sync() -> list[str]:
    """Delegate wiki drift detection to wiki-sync.py."""
    issues = []
    script = V.AIOS_DIR / "tools" / "wiki" / "wiki-sync.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            for line in result.stdout.splitlines():
                if "Summary:" in line:
                    issues.append(f"[STALE] wiki drift detected: {line.strip()}")
    except FileNotFoundError:
        issues.append("[STALE] wiki-sync.py not found — cannot check sync status")
    except subprocess.TimeoutExpired:
        issues.append("[STALE] wiki-sync timed out")
    return issues


def check_missing_sources(notes: list[dict]) -> list[str]:
    """Notes citing nothing.

    Clippings cite their origin in `source:` (singular) — that IS their traceability.
    note-review.py applies the same exemption; without it the two tools disagree about
    the same file (atlas/apis clippings scored EXCELLENT there and INFO here).
    """
    issues = []
    for n in notes:
        if not n["body"]:
            continue
        fm = n["frontmatter"]
        if fm.get("sources") or (V.is_clipping(n) and fm.get("source")):
            continue
        issues.append(f"[INFO] {n['path']}: no sources cited")
    return issues


def workdays_between(start: datetime.date, end: datetime.date) -> int:
    """Mon–Fri days after `start` up to and including `end`."""
    days, d = 0, start
    while d < end:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def check_retire_due(notes: list[dict], today: datetime.date | None = None) -> list[str]:
    """Shipped efforts past their whole-note window that are not yet a stub.

    Informational, not blocking: the stub is written in a session with a human present
    (every claim re-verified against code before it moves to atlas), so this only says
    which notes are due. A note with `stub:` set is already retired.
    """
    today = today or datetime.date.today()
    threshold = int((V.CONFIG.get("efforts") or {}).get("stubAfterWorkdays", 14))
    issues = []
    for n in notes:
        fm = n["frontmatter"]
        if not n["path"].startswith("efforts/works/") or str(fm.get("status", "")).strip() != "shipped":
            continue
        if str(fm.get("stub", "")).strip():
            continue
        raw = str(fm.get("shipped", "")).strip()
        try:
            shipped = datetime.date.fromisoformat(raw)
        except ValueError:
            issues.append(
                f"[INFO] RETIRE {n['path']}: status is shipped but `shipped:` is "
                f"{'missing' if not raw else f'not a date ({raw})'} — add the ship date"
            )
            continue
        age = workdays_between(shipped, today)
        if age >= threshold:
            issues.append(
                f"[INFO] RETIRE {n['path']}: shipped {shipped}, {age} workdays ago "
                f"(stub after {threshold}) — distil into atlas and replace with a stub"
            )
    return issues


def run_checks(notes: list[dict], with_wiki: bool = True) -> list[str]:
    issues: list[str] = []
    issues += check_required_fields(notes)
    issues += check_broken_wikilinks(notes)
    issues += check_orphans(notes)
    issues += check_inbox_links(notes)
    issues += check_note_kinds(notes)
    issues += check_empty_notes(notes)
    issues += check_duplicate_basenames(notes)
    if with_wiki:
        issues += check_wiki_sync()
    issues += check_missing_sources(notes)
    issues += check_retire_due(notes)
    return issues


# ── Coverage stats ─────────────────────────────────────────────

def print_categories(notes: list[dict]):
    subcats: dict[str, dict[str, list[str]]] = {}
    for n in notes:
        parts = n["path"].split("/")
        top = parts[0] if len(parts) >= 2 else "(root)"
        sub = parts[1] if len(parts) >= 3 else "(direct)"
        subcats.setdefault(top, {}).setdefault(sub, []).append(n["path"])

    print("\n── Category coverage ──\n")
    for top in sorted(subcats):
        print(f"  {top}/")
        for sub in sorted(subcats[top]):
            print(f"    {sub}/ — {len(subcats[top][sub])} note(s)")


def print_summary(issues: list[str], notes: list[dict]):
    counts = {
        p: sum(1 for i in issues if i.startswith(f"[{p}]"))
        for p in ("FATAL", "BROKEN", "ORPHAN", "INBOX-LINK", "DOC-KIND", "CONCEPT-KIND", "EMPTY", "DUPE", "STALE", "INFO")
    }
    parts = [
        f"{counts[k]} {label}"
        for k, label in (
            ("FATAL", "fatal"), ("BROKEN", "broken links"), ("ORPHAN", "orphans"),
            ("INBOX-LINK", "inbox links"), ("DOC-KIND", "document kinds"),
            ("CONCEPT-KIND", "concept kinds"),
            ("EMPTY", "empty"), ("DUPE", "duplicates"), ("STALE", "stale wiki"),
        )
        if counts[k]
    ]
    severity = "clean" if not parts else "ISSUES FOUND"
    print(
        f"\nSummary: {severity} — {len(notes)} notes scanned, "
        f"{counts['INFO']} info" + (f", {', '.join(parts)}" if parts else "")
    )


# ── Auto-fix ───────────────────────────────────────────────────

def apply_fixes(notes: list[dict]) -> int:
    """Add a missing 'created' field to notes that are otherwise well-formed."""
    fixed = 0
    today = datetime.date.today().isoformat()
    for n in notes:
        fm = n["frontmatter"]
        if "created" in fm:
            continue
        anchor = "related" if "related" in fm else ("source" if "source" in fm else None)
        if anchor is None:
            continue
        text = n["abspath"].read_text(encoding="utf-8")
        lines, out, done = text.split("\n"), [], False
        for line in lines:
            out.append(line)
            if not done and re.match(rf"^\s*{anchor}:\s*", line):
                out.append(f"created: {today}")
                done = True
        if done:
            n["abspath"].write_text("\n".join(out), encoding="utf-8")
            fixed += 1
    return fixed


# ── Main ───────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        # No abbreviations: `--fi` must not silently become `--fix`.
        # inspector-scope.py allowlists the flags a reviewer may pass, and argparse
        # accepting a prefix would let one through a reviewer never typed.
        allow_abbrev=False, description="IdeaVerse structural health check & lint.")
    ap.add_argument("-q", "--quiet", action="store_true", help="Print only the summary line.")
    ap.add_argument("-f", "--fix", action="store_true", help="Auto-fix missing 'created' fields.")
    ap.add_argument("-c", "--categories", action="store_true", help="Print category coverage table.")
    args = ap.parse_args()

    notes = V.load_notes()
    if not notes:
        print(f"[FATAL] no notes found at {V.IDEAVERSE_DIR}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"vault-lint   ({V.IDEAVERSE_DIR}) — {len(notes)} notes scanned\n")

    if args.fix:
        fixed = apply_fixes(notes)
        if fixed:
            print(f"✓ Fixed {fixed} note(s): added missing 'created' field.\n")
        notes = V.load_notes()

    issues = run_checks(notes)
    has_issues = any(not i.startswith("[INFO]") for i in issues)

    if not args.quiet:
        for prefix in ("FATAL", "BROKEN", "ORPHAN", "INBOX-LINK", "DOC-KIND", "CONCEPT-KIND", "EMPTY", "DUPE", "STALE"):
            items = [i for i in issues if i.startswith(f"[{prefix}]")]
            if items:
                print(f"  {prefix} ({len(items)})")
                for item in items:
                    print(f"    {item}")
                print()

        info_items = [i for i in issues if i.startswith("[INFO]")]
        if info_items:
            print(f"  INFO ({len(info_items)} — informational, not blocking)")
            for item in info_items:
                print(f"    {item}")
            print()

        if args.categories:
            print_categories(notes)

    # The summary line is the whole point of --quiet, so it prints in both modes.
    print_summary(issues, notes)

    return 1 if has_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
