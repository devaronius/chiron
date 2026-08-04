#!/usr/bin/env python3
"""
wiki-sync — detect ideaVerse source changes that need (re)compiling into the wiki.

It compares the raw source notes under ideaVerse/ against:
  1. a content-hash manifest (wiki/.wiki-sync.json) snapshotted at the last compile, and
  2. the wiki catalog (wiki/wiki.catalog.jsonl), whose `sources[]` say which note(s)
     each source was compiled into.

and reports four states:
  + NEW       source exists, no manifest entry      → needs a new wiki note
  ~ CHANGED   content hash differs from manifest     → wiki note(s) may be stale
  - DELETED   manifest entry, file gone              → wiki note(s) orphaned
    UNCOVERED source not cited by any wiki note      → never compiled

It does NOT write wiki notes (compilation is a judgment call). After you reconcile
the wiki, run `--update` to re-snapshot the manifest as the new baseline.

Lives in <vault>/aiOS/scripts/ but operates on wiki/ + ideaVerse/ —
locations are resolved relative to the vault root, so it runs from any working directory.

Usage:
  python3 <vault>/aiOS/scripts/wiki-sync.py            # check; exits 1 if drift is found
  python3 <vault>/aiOS/scripts/wiki-sync.py --update   # re-snapshot the manifest (new baseline)
  python3 <vault>/aiOS/scripts/wiki-sync.py --quiet    # only print the summary line
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

VAULT_DIR = Path(__file__).resolve().parents[2]       # <vault>/aiOS/scripts -> <vault>
WIKI_DIR = VAULT_DIR / "wiki"
IDEAVERSE_DIR = VAULT_DIR / "ideaVerse"
CATALOG = WIKI_DIR / "wiki.catalog.jsonl"
MANIFEST = WIKI_DIR / ".wiki-sync.json"               # baseline lives with the wiki


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def scan_sources() -> dict[str, dict]:
    """All *.md under ideaVerse, keyed by path relative to ideaVerse root."""
    out: dict[str, dict] = {}
    if not IDEAVERSE_DIR.is_dir():
        sys.exit(f"ideaVerse not found at {IDEAVERSE_DIR}")
    for p in sorted(IDEAVERSE_DIR.rglob("*.md")):
        rel = p.relative_to(IDEAVERSE_DIR).as_posix()
        out[rel] = {"sha256": sha256(p), "size": p.stat().st_size}
    return out


def load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text()).get("files", {})


def load_catalog_coverage() -> dict[str, list[str]]:
    """Map a source token (basename, with and without .md) -> [note ids that cite it]."""
    cover: dict[str, list[str]] = {}
    if not CATALOG.exists():
        return cover
    for line in CATALOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        for src in row.get("sources", []):
            cover.setdefault(src.lower(), []).append(row["id"])
    return cover


def notes_for(rel_path: str, cover: dict[str, list[str]]) -> list[str]:
    """Which wiki notes cite this source file."""
    name = Path(rel_path).name                 # e.g. app_structure.md
    stem = Path(rel_path).stem                  # e.g. app_structure
    hits: list[str] = []
    for token in (name.lower(), stem.lower()):
        hits += cover.get(token, [])
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser(description="Check ideaVerse sources against the compiled wiki.")
    ap.add_argument("-u", "--update", action="store_true",
                    help="Re-snapshot the manifest to the current ideaVerse state (new baseline).")
    ap.add_argument("-q", "--quiet", action="store_true", help="Print only the summary line.")
    args = ap.parse_args()

    current = scan_sources()
    manifest = load_manifest()
    cover = load_catalog_coverage()

    cur_keys, man_keys = set(current), set(manifest)
    new = sorted(cur_keys - man_keys)
    deleted = sorted(man_keys - cur_keys)
    changed = sorted(k for k in (cur_keys & man_keys)
                     if current[k]["sha256"] != manifest[k]["sha256"])
    unchanged = sorted(k for k in (cur_keys & man_keys)
                       if current[k]["sha256"] == manifest[k]["sha256"])
    # Sources present on disk that no wiki note cites (regardless of manifest state).
    uncovered = sorted(k for k in cur_keys if not notes_for(k, cover))

    first_run = not MANIFEST.exists()

    if args.update:
        MANIFEST.write_text(json.dumps(
            {"generated": datetime.date.today().isoformat(), "files": current},
            indent=2, sort_keys=True) + "\n")
        print(f"✓ Snapshotted {len(current)} source files → {MANIFEST}")
        return 0

    drift = bool(new or changed or deleted)

    if not args.quiet:
        print(f"Wiki ↔ ideaVerse sync   ({IDEAVERSE_DIR})\n")
        if first_run:
            print("⚠ No manifest yet — 'NEW/CHANGED/DELETED' can't be computed.")
            print("  Run with `--update` to create the baseline.\n")

        def block(title: str, items: list[str], show_notes: bool):
            if not items:
                return
            print(f"{title} ({len(items)})")
            for k in items:
                print(f"  {k}")
                if show_notes:
                    n = notes_for(k, cover)
                    print(f"      affects: {', '.join(n) if n else '(no wiki note — needs compiling)'}")
            print()

        if not first_run:
            block("＋ NEW (needs a wiki note)", new, show_notes=False)
            block("～ CHANGED (wiki note may be stale)", changed, show_notes=True)
            block("－ DELETED (wiki note orphaned)", deleted, show_notes=True)
        block("• UNCOVERED (no wiki note cites this source)", uncovered, show_notes=False)
        if not first_run:
            print(f"  unchanged: {len(unchanged)}")

    print(f"\nSummary: {len(new)} new, {len(changed)} changed, {len(deleted)} deleted, "
          f"{len(uncovered)} uncovered"
          + (".  Run with --update after reconciling the wiki." if drift else ".  Wiki is in sync."))

    return 1 if (drift and not first_run) else 0


if __name__ == "__main__":
    raise SystemExit(main())
