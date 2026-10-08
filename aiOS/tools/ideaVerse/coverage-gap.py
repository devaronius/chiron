#!/usr/bin/env python3
"""
coverage-gap — find what the ideaVerse does not yet document.

Two independent gap classes, deliberately kept separate because they fail for
different reasons and are fixed by different work:

  CODE-ANCHORED — the vault drifting behind the repo. Every check here is driven by
  the `code` block in aios.config.json and is skipped when the key it needs is unset,
  so a vault over a repo this does not describe reports nothing rather than nonsense.
    * every package in <packageDir>/ and app in <appDir>/ should have an entity note
    * an entity note matching `packagePattern` whose package is gone is a STALE note
    * every API class (a file containing `apiClassMarker`) should have a documented contract
    * every feature dir (<packageDir>/*/<featureDir>/*) should be named in the vault
  The code is the final authority over the vault, so code without a note is the drift
  that matters.

  CALENDAR-COMPLETENESS — holes in the framework's own cadence.
    * every working day (Mon–Fri) since the first day note has a day note
    * every working day since the first briefing has a briefing
    A day inside a declared absence (`calendar.absences` in aios.config.json) is not
    a working day and is not reported — nobody was there to keep the record. The
    ranges and the day counts they removed are printed with the report, so the check
    can be seen to have been narrowed rather than quietly weakened.
    * every sprint referenced by a day note actually exists (day notes parent to their
      sprint note; the ISO week-note tier was retired 2026-07-29 — a sprint spans exactly
      two aligned ISO weeks, so a week note was half a sprint note on the same boundaries)

  Both are bounded by the EARLIEST existing note of each kind, so the script reports
  holes in the period actually being kept — never "you are missing 2019".

Explicitly NOT checked: whether ideaVerse notes are compiled into the wiki.
wiki-sync.py owns that; duplicating it would give two tools that can disagree.

Usage:
  python3 aiOS/tools/ideaVerse/coverage-gap.py
  python3 aiOS/tools/ideaVerse/coverage-gap.py --json        # machine-readable
  python3 aiOS/tools/ideaVerse/coverage-gap.py --code        # code-anchored gaps only
  python3 aiOS/tools/ideaVerse/coverage-gap.py --calendar    # calendar gaps only

Exit codes:
  0 — no gaps
  1 — gaps found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

# Project-shaped values come from aios.config.json rather than being repeated here.
# They were declared there and duplicated as literals in this file, so the config was
# dead and the literals were the truth — a config that cannot change behaviour is worse
# than no config, because it reads as though it can.
_CODE = V.CONFIG["code"]
# No language defaults: an unset key means "this repo is not shaped that way", and a
# check that cannot be configured off reports every file in the repo as a gap.
SOURCE_EXT = _CODE.get("sourceExt", "")
TEST_SUFFIX = _CODE.get("testSuffix", "")
API_CLASS_MARKER = _CODE.get("apiClassMarker", "")
FEATURE_DIR = _CODE.get("featureDir", "")
# Basenames an entity note may carry for a package that must exist — the stale-note
# direction of the package check. Unset means the check is off: without a pattern every
# note in the vault looks like it might name a package.
PACKAGE_PATTERN = _CODE.get("packagePattern", "")
# API classes that are the base class or a test double, not a contract.
API_CLASS_EXCLUDE = set(_CODE.get("apiClassExclude", []))

PACKAGE_DIR = _CODE.get("packageDir", "")
APP_DIR = _CODE.get("appDir", "")
MODULES_DIR = V.REPO_ROOT / PACKAGE_DIR if PACKAGE_DIR else None
APPS_DIR = V.REPO_ROOT / APP_DIR if APP_DIR else None

DAYS_DIR = V.IDEAVERSE_DIR / "calendar" / "days"
BRIEFINGS_DIR = V.IDEAVERSE_DIR / "calendar" / "briefings"

# An app package maps to an entity note with this suffix by convention
# (<appDir>/shop -> shop-app).
APP_NOTE_SUFFIX = _CODE.get("appNoteSuffix", "-app")


# ── Inventory helpers ──────────────────────────────────────────

def repo_packages() -> tuple[set[str], set[str]]:
    """(module package names, app package names) actually present in the repo."""
    mods = {p.name for p in MODULES_DIR.iterdir() if p.is_dir()} \
        if MODULES_DIR and MODULES_DIR.is_dir() else set()
    apps = {p.name for p in APPS_DIR.iterdir() if p.is_dir()} \
        if APPS_DIR and APPS_DIR.is_dir() else set()
    return mods, apps


def api_classes() -> set[str]:
    """Basenames of source files containing the configured API-class marker."""
    found = set()
    if not (API_CLASS_MARKER and SOURCE_EXT):
        return found
    for root in (MODULES_DIR, APPS_DIR):
        if not (root and root.is_dir()):
            continue
        for p in root.rglob(f"*{SOURCE_EXT}"):
            if TEST_SUFFIX and p.name.endswith(TEST_SUFFIX):
                continue
            try:
                if API_CLASS_MARKER in p.read_text(encoding="utf-8", errors="ignore"):
                    found.add(p.stem)
            except OSError:
                continue
    return found - API_CLASS_EXCLUDE


def feature_dirs() -> set[tuple[str, str]]:
    """(package, feature) for every <packageDir>/*/<featureDir>/<feature>/."""
    feats = set()
    if not (FEATURE_DIR and MODULES_DIR and MODULES_DIR.is_dir()):
        return feats
    for mod in MODULES_DIR.iterdir():
        fd = mod / FEATURE_DIR
        if fd.is_dir():
            feats |= {(mod.name, f.name) for f in fd.iterdir() if f.is_dir()}
    return feats


def vault_corpus(notes: list[dict]) -> str:
    """All vault + wiki text, lowercased, for 'is this named anywhere?' checks."""
    parts = [n["body"] for n in notes] + [n["basename"] for n in notes]
    for p in V.WIKI_DIR.rglob("*.md"):
        try:
            parts.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(parts).lower()


def documented_basenames() -> set[str]:
    """Every note basename in the vault — the set an entity note can live in."""
    return V.resolvable_basenames()


# ── Code-anchored gaps ─────────────────────────────────────────

def check_packages(names: set[str]) -> list[dict]:
    """Packages without an entity note, and entity notes for absent packages."""
    gaps = []
    mods, apps = repo_packages()

    for m in sorted(mods):
        if m not in names:
            gaps.append({
                "type": "module-note-missing", "item": m, "severity": "high",
                "detail": f"{PACKAGE_DIR}/{m}/ has no entity note",
            })
    for a in sorted(apps):
        if a + APP_NOTE_SUFFIX not in names and a not in names:
            gaps.append({
                "type": "app-note-missing", "item": a, "severity": "high",
                "detail": f"{APP_DIR}/{a}/ has no entity note (expected '{a}{APP_NOTE_SUFFIX}')",
            })

    # Reverse direction: an entity note shaped like a package name whose package is gone.
    for n in sorted(names) if PACKAGE_PATTERN else []:
        if re.fullmatch(PACKAGE_PATTERN, n) and n not in mods:
            gaps.append({
                "type": "note-stale-package", "item": n, "severity": "medium",
                "detail": f"entity note '{n}' names a package absent from {PACKAGE_DIR}/",
            })
    return gaps


def check_api_contracts(notes: list[dict], corpus: str) -> list[dict]:
    """API classes with no documented contract anywhere in the vault."""
    clippings = {n["basename"] for n in notes if n["path"].startswith("atlas/apis/")}
    gaps = []
    for cls in sorted(api_classes()):
        # The clipping is usually filed under the service, not the class: strip the
        # trailing marker word so `billing_api` also matches a note named `billing`.
        service = re.sub(r"_api$", "", cls)
        named = cls in corpus or any(service and service in c for c in clippings)
        if not named:
            gaps.append({
                "type": "api-undocumented", "item": cls, "severity": "medium",
                "detail": f"{cls}{SOURCE_EXT} matches '{API_CLASS_MARKER}' but is never named in the vault",
            })
    return gaps


def check_features(corpus: str) -> list[dict]:
    """Feature dirs never mentioned in the vault."""
    gaps = []
    for mod, feat in sorted(feature_dirs()):
        if feat.lower() not in corpus:
            gaps.append({
                "type": "feature-undocumented", "item": f"{mod}/{feat}", "severity": "low",
                "detail": f"{PACKAGE_DIR}/{mod}/{FEATURE_DIR}/{feat}/ is not named anywhere in the vault",
            })
    return gaps


# ── Calendar-completeness gaps ─────────────────────────────────

DATE_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def existing_dates(d: Path) -> list[date]:
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.md"):
        m = DATE_NAME_RE.match(p.stem)
        if m:
            out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return sorted(out)


def absences() -> list[tuple[date, date, str]]:
    """Declared absence ranges from `calendar.absences`, both ends inclusive.

    A malformed entry is dropped rather than raised on: a typo in the config must
    not take the whole coverage check offline, and a dropped range simply shows up
    as the gaps it would have hidden.
    """
    out = []
    for e in (V.CONFIG.get("calendar") or {}).get("absences", []):
        try:
            out.append((
                date.fromisoformat(e["from"]),
                date.fromisoformat(e["to"]),
                str(e.get("why", "")).strip(),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def working_days(start: date, end: date) -> list[date]:
    """Mon–Fri between the bounds, minus any day inside a declared absence.

    A day nobody worked is not a hole in the record. The absence has to be declared
    in `aios.config.json` — the check is never silently narrowed, and `format_report`
    says how many days each range removed.
    """
    away = absences()
    out, cur = [], start
    while cur <= end:
        if cur.weekday() < 5 and not any(a <= cur <= b for a, b, _ in away):  # Mon–Fri
            out.append(cur)
        cur += timedelta(days=1)
    return out


def check_day_notes() -> list[dict]:
    have = existing_dates(DAYS_DIR)
    if not have:
        return []
    gaps = []
    for d in working_days(have[0], V.today()):
        if d not in have:
            gaps.append({
                "type": "day-note-missing", "item": d.isoformat(), "severity": "medium",
                "detail": f"no calendar/days/{d.isoformat()}.md for this working day",
            })
    return gaps


SPRINT_LINK_RE = re.compile(r"\[\[([^\]|]*?sprint\s*\d+)(?:\|[^\]]+)?\]\]", re.IGNORECASE)


def check_sprint_parents() -> list[dict]:
    """Sprint notes that day notes/briefings link to as their parent but which don't exist.

    Day notes parent to their sprint note. A sprint stub should exist from the sprint's
    first day, so the link resolves mid-sprint rather than only once it is written up.
    """
    known = V.resolvable_basenames()
    wanted: dict[str, list[str]] = {}
    for d in (DAYS_DIR, BRIEFINGS_DIR):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            for m in SPRINT_LINK_RE.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                target = m.group(1).strip()
                if target not in known:
                    wanted.setdefault(target, []).append(p.name)
    return [
        {
            "type": "sprint-note-missing", "item": target, "severity": "high",
            "detail": f"{len(srcs)} day/briefing note(s) link [[{target}]] but it does not exist",
        }
        for target, srcs in sorted(wanted.items())
    ]


def check_briefings() -> list[dict]:
    have = existing_dates(BRIEFINGS_DIR)
    if not have:
        return []
    gaps = []
    for d in working_days(have[0], V.today()):
        if d not in have:
            gaps.append({
                "type": "briefing-missing", "item": d.isoformat(), "severity": "low",
                "detail": f"no calendar/briefings/{d.isoformat()}.md for this working day",
            })
    return gaps


# ── Report ─────────────────────────────────────────────────────

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
GROUPS = {
    "module-note-missing": "Code-anchored — packages",
    "app-note-missing": "Code-anchored — packages",
    "note-stale-package": "Code-anchored — packages",
    "api-undocumented": "Code-anchored — API contracts",
    "feature-undocumented": "Code-anchored — features",
    "day-note-missing": "Calendar — day notes",
    "briefing-missing": "Calendar — briefings",
    "sprint-note-missing": "Calendar — sprint parents",
}


def collect(want_code: bool, want_calendar: bool) -> list[dict]:
    notes = V.load_notes()
    gaps: list[dict] = []
    if want_code:
        names = documented_basenames()
        corpus = vault_corpus(notes)
        gaps += check_packages(names)
        gaps += check_api_contracts(notes, corpus)
        gaps += check_features(corpus)
    if want_calendar:
        gaps += check_day_notes()
        gaps += check_briefings()
        gaps += check_sprint_parents()
    return sorted(gaps, key=lambda g: (SEV_ORDER.get(g["severity"], 3), g["type"], g["item"]))


def absence_lines() -> list[str]:
    """Say what the calendar checks skipped. Silent suppression is the failure mode."""
    away = absences()
    if not away:
        return []
    out = ["Calendar absences honoured (declared in aios.config.json):"]
    for a, b, why in away:
        days = len(working_days_raw(a, b))
        out.append(f"  {a} → {b} — {days} working day(s) skipped"
                   + (f" · {why}" if why else ""))
    out.append("")
    return out


def working_days_raw(start: date, end: date) -> list[date]:
    """Mon–Fri with no absence filtering — used only to count what an absence removed."""
    out, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def vacuous_lines() -> list[str]:
    """Say which configured detectors matched nothing.

    A check that finds no input reports success, which is indistinguishable from a
    check that passed — that is how `kanban-sync.py` reconciled a board this repo never
    had, from three call sites, for months. So a marker that matches zero files says so
    out loud rather than folding silently into a COMPLETE verdict.
    """
    out = []
    if API_CLASS_MARKER and not api_classes():
        out.append(f"  · apiClassMarker {API_CLASS_MARKER!r} matched 0 files — "
                   "that check inspected nothing")
    # A detector with no config is switched off, not blind: saying it "inspected nothing"
    # would report an unconfigured vault as a problem on every run.
    if FEATURE_DIR and not feature_dirs():
        out.append(f"  · no package has a {FEATURE_DIR}/ directory — "
                   "the feature check inspected nothing")
    return ["Detectors that matched nothing (not a gap — a blind spot):", *out, ""] if out else []


def format_report(gaps: list[dict], note_count: int) -> str:
    lines = [f"Coverage Analysis — {note_count} notes scanned"]
    if not gaps:
        lines.append("Health: COMPLETE\n")
        lines += absence_lines()
        lines += vacuous_lines()
        lines.append("✓ No coverage gaps found.")
        return "\n".join(lines)

    high = sum(1 for g in gaps if g["severity"] == "high")
    lines.append(f"Health: {'NEEDS ATTENTION' if high else 'MINOR GAPS'}")
    lines.append(f"Total gaps: {len(gaps)}\n")
    lines += absence_lines()
    lines += vacuous_lines()

    seen_groups: dict[str, list[dict]] = {}
    for g in gaps:
        seen_groups.setdefault(GROUPS.get(g["type"], "Other"), []).append(g)

    for group in sorted(seen_groups):
        items = seen_groups[group]
        lines.append(f"{group}: {len(items)}")
        for g in items:
            mark = {"high": "!!", "medium": " !", "low": "  "}[g["severity"]]
            lines.append(f"  {mark} {g['item']} — {g['detail']}")
        lines.append("")

    lines.append("Fix order: high severity first (code the vault does not describe at all),")
    lines.append("then calendar holes, then low-severity naming gaps.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Find undocumented code and calendar holes.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    ap.add_argument("--code", action="store_true", help="Code-anchored gaps only.")
    ap.add_argument("--calendar", action="store_true", help="Calendar gaps only.")
    args = ap.parse_args()

    want_code = args.code or not args.calendar
    want_calendar = args.calendar or not args.code

    gaps = collect(want_code, want_calendar)
    note_count = len(V.load_notes())

    if args.json:
        print(json.dumps({"total": len(gaps), "gaps": gaps}, indent=2))
    else:
        print(format_report(gaps, note_count))
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
