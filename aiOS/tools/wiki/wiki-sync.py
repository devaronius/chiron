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

Lives in aiOS/tools/wiki/ but operates on wiki/ + ideaVerse/ —
locations are resolved relative to the vault root, so it runs from any working directory.

Usage:
  python3 aiOS/tools/wiki/wiki-sync.py            # check; exits 1 if drift is found
  python3 aiOS/tools/wiki/wiki-sync.py --update   # re-snapshot the manifest (new baseline)
  python3 aiOS/tools/wiki/wiki-sync.py --quiet    # only print the summary line
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

# Layout comes from vault_lib in the sibling tools/ideaVerse group — one definition of
# where the vault is, rather than a second copy that can drift from it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ideaVerse"))
import vault_lib as V  # noqa: E402

VAULT_DIR = V.VAULT_DIR
WIKI_DIR = V.WIKI_DIR
IDEAVERSE_DIR = V.IDEAVERSE_DIR
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


# A CHANGED source says its *source* moved. It cannot say whether the compiled note
# was actually reconciled, because the manifest hashes sources and never looks at the
# summary. That gap is how a compiled note kept recommending an option its source had
# reversed two revisions earlier: the paragraph in hand was fixed, `--update` was run,
# and every other paragraph was silently baselined as current.
#
# `updated:` is the cheapest available proxy. The vault already requires it to be
# bumped in the same commit as any edit (vault-map, "What created: and updated: mean"),
# so a compiled note whose source moved while its own `updated:` did not is a note
# nobody re-read.
UPDATED_RE = re.compile(r'^updated:\s*(\d{4}-\d{2}-\d{2})', re.M)


def updated_of(path: Path) -> str:
    try:
        head = path.read_text(encoding='utf-8')[:1200]
    except OSError:
        return ''
    found = UPDATED_RE.search(head)
    return found.group(1) if found else ''


def unreconciled(changed: list[str], cover: dict[str, list[str]],
                 catalog_path: Path) -> list[tuple[str, str]]:
    """(source, note) pairs where the source moved but its summary's `updated:` did not.

    Compared against the *sources* own `updated:`: if the compiled note is older than
    the source it summarises, the edit has not reached it.
    """
    out = []
    for rel in changed:
        src_date = updated_of(IDEAVERSE_DIR / rel)
        if not src_date:
            continue
        for note in notes_for(rel, cover):
            note_path = catalog_path.parent / f'{note}.md'
            if not note_path.exists():
                matches = list(catalog_path.parent.rglob(f'{note}.md'))
                if not matches:
                    continue
                note_path = matches[0]
            note_date = updated_of(note_path)
            if note_date and note_date < src_date:
                out.append((rel, f'{note} (updated {note_date} < source {src_date})'))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        # No abbreviations: `--up` must not silently become `--update`.
        # inspector-scope.py allowlists the flags a reviewer may pass, and argparse
        # accepting a prefix would let one through a reviewer never typed.
        allow_abbrev=False, description="Check ideaVerse sources against the compiled wiki.")
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
            stale = unreconciled(changed, cover, CATALOG)
            if stale:
                print(f"✗ NOT RECONCILED ({len(stale)})")
                for source, note in stale:
                    print(f"  {source}")
                    print(f"      {note}")
                print("  The source moved and its summary did not. Re-read the note end to "
                      "end before --update, or the rest of it is baselined as current.\n")
            print(f"  unchanged: {len(unchanged)}")

    # Counted again here rather than passed down, so the summary cannot drift from the
    # block above it. It belongs on this line because this is the line a caller piping
    # through `tail` actually sees — a report printed only further up is a report that
    # gets run past.
    stale_now = unreconciled(changed, cover, CATALOG) if not first_run else []
    alarm = (f", ⚠ {len(stale_now)} NOT RECONCILED" if stale_now else "")
    print(f"\nSummary: {len(new)} new, {len(changed)} changed, {len(deleted)} deleted, "
          f"{len(uncovered)} uncovered{alarm}"
          + (".  Run with --update after reconciling the wiki." if drift else ".  Wiki is in sync."))

    return 1 if (drift and not first_run) else 0


if __name__ == "__main__":
    raise SystemExit(main())
