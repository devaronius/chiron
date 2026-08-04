#!/usr/bin/env python3
"""
chiron-release — cut a chiron release: bump VERSION, refresh the shipped-hash history,
and check that the CHANGELOG actually documents it.

Not payload. Lives in `tools/`, never copied into a consumer vault.

`.chiron-hashes.json` maps each payload path to every hash chiron has ever shipped for it:

    { "aiOS/scripts/wiki-sync.py": { "0.9.0": "abc…", "1.0.0": "f01…" } }

It accumulates — each release adds one entry per payload file and never drops an old one.
That history is what lets `chiron-install.py` adopt a vault with no manifest: a file whose
hash appears anywhere in it was shipped by us and is therefore safe to overwrite, while a
hash that appears nowhere is the user's own work and must be left alone. Dropping old
entries to keep the file small would silently reclassify every older install's untouched
files as conflicts.

It is committed rather than derived from git tags at install time, so a `--depth 1` clone
adopts just as correctly as a full one.

Usage:
  chiron-release.py --bump patch|minor|major
  chiron-release.py --set 1.2.0
  chiron-release.py --check                 # verify hashes are current for this VERSION
  chiron-release.py --seed LABEL --from DIR # record a historical generation (see below)

`--seed` records the hashes of a directory tree as a named generation without touching
VERSION. Used once, to teach the history what pre-chiron installs look like so they can be
adopted rather than reported as one giant conflict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

CHIRON_ROOT = Path(__file__).resolve().parents[1]
HASHES_PATH = CHIRON_ROOT / ".chiron-hashes.json"
VERSION_PATH = CHIRON_ROOT / "VERSION"
CHANGELOG_PATH = CHIRON_ROOT / "CHANGELOG.md"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib.machinery import SourceFileLoader  # noqa: E402

_installer = SourceFileLoader(
    "chiron_install", str(Path(__file__).resolve().parent / "chiron-install.py")).load_module()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def payload_paths() -> list[str]:
    """Every payload file, as a path relative to the chiron root.

    Reuses the installer's own walk so the two can never disagree about what ships.
    """
    out = []
    for name in ("aiOS", "seeds"):
        d = CHIRON_ROOT / name
        if d.is_dir():
            out += [p.relative_to(CHIRON_ROOT).as_posix() for p in _installer.walk(d)]
    skills = CHIRON_ROOT / "skills"
    if skills.is_dir():
        for sd in sorted(x for x in skills.iterdir() if x.is_dir()):
            out += [p.relative_to(CHIRON_ROOT).as_posix() for p in _installer.walk(sd)]
    return sorted(out)


def record(label: str, root: Path, rel_paths: list[str] | None = None) -> tuple[int, int]:
    history = _installer.read_json(HASHES_PATH, {})
    added = skipped = 0
    for rel in (rel_paths if rel_paths is not None else payload_paths()):
        p = root / rel
        if not p.is_file():
            skipped += 1
            continue
        history.setdefault(rel, {})[label] = sha(p.read_bytes())
        added += 1
    HASHES_PATH.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return added, skipped


def check(v: str) -> int:
    history = _installer.read_json(HASHES_PATH, {})
    stale = []
    for rel in payload_paths():
        want = sha((CHIRON_ROOT / rel).read_bytes())
        if history.get(rel, {}).get(v) != want:
            stale.append(rel)
    if stale:
        print(f"✗ {len(stale)} payload file(s) not recorded at {v}:")
        for s in stale[:20]:
            print(f"   {s}")
        print("   run: chiron-release.py --set " + v)
        return 1
    print(f"✓ hash history is current for {v} ({len(payload_paths())} payload files)")
    return 0


def bump(v: str, part: str) -> str:
    major, minor, patch = (list(map(int, re.findall(r"\d+", v))) + [0, 0, 0])[:3]
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Cut a chiron release.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bump", choices=["major", "minor", "patch"])
    g.add_argument("--set", dest="set_to")
    g.add_argument("--check", action="store_true")
    g.add_argument("--seed", metavar="LABEL")
    ap.add_argument("--from", dest="from_dir", help="directory tree to hash (with --seed)")
    args = ap.parse_args()

    if args.check:
        return check(read_version())

    if args.seed:
        if not args.from_dir:
            print("✗ --seed needs --from DIR", file=sys.stderr)
            return 2
        root = Path(args.from_dir).expanduser().resolve()
        added, skipped = record(args.seed, root)
        print(f"✓ recorded generation {args.seed} from {root}: {added} file(s), {skipped} absent")
        return 0

    new = args.set_to or bump(read_version(), args.bump)
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        print(f"✗ not a semver: {new}", file=sys.stderr)
        return 2

    changelog = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else ""
    if f"## [{new}]" not in changelog:
        print(f"✗ CHANGELOG.md has no `## [{new}]` section — write it before releasing.",
              file=sys.stderr)
        return 1

    VERSION_PATH.write_text(new + "\n", encoding="utf-8")
    added, _ = record(new, CHIRON_ROOT)
    print(f"✓ VERSION → {new}; recorded {added} payload file(s) in .chiron-hashes.json")
    print(f"  next: git commit -am 'chore: release {new}' && git tag v{new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
