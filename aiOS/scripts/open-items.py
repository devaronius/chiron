#!/usr/bin/env python3
"""
open-items — scan the ideaVerse for open items and compile the open-items ledger.

An *open item* (see ideaVerse/atlas/concepts/open_item.md) is a Markdown task
line carrying Dataview inline fields, e.g.:

    - [ ] Wire the export endpoint [status:: open] [due:: 2026-07-31] [raised:: 2026-07-08]

This script walks ideaVerse/, finds every line with a `[status:: …]` field,
computes each item's age from `raised::`, de-duplicates items that appear in more
than one note (preferring a non-calendar owner), and writes a single ledger view to
open-items.md — a static Markdown table (durable everywhere) plus a Dataview
block (live in Obsidian). It is a *view generator*; the source of truth stays in the
owning effort/project notes.

Kept separate from wiki-sync.py on purpose: that script detects wiki drift, this one
compiles a task view — different jobs, different outputs.

Usage:
  python3 <vault>/aiOS/scripts/open-items.py                 # write open-items.md
  python3 <vault>/aiOS/scripts/open-items.py --today 2026-07-08   # pin "today" (aging)
  python3 <vault>/aiOS/scripts/open-items.py --check         # print, don't write (exit 1 if changed)
  python3 <vault>/aiOS/scripts/open-items.py --include-done   # also list done items
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

VAULT_DIR = Path(__file__).resolve().parents[2]        # <vault>/aiOS/scripts -> <vault>
IDEAVERSE_DIR = VAULT_DIR / "ideaVerse"
LEDGER = VAULT_DIR / "open-items.md"

# Dataview resolves FROM against the Obsidian vault root, which is the repo root — so the
# source path carries the vault directory unless the vault IS the repo root.
DATAVIEW_SOURCE = V.vault_rel("ideaVerse")

CALLOUT_RE = re.compile(r"^\s*(?:>\s?)+")            # strip callout '>' prefixes
FENCE_RE = re.compile(r"^\s*(?:>\s?)*```")           # code-fence toggle
TASK_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.*)$")
FIELD_RE = re.compile(r"\[(status|due|raised|owner|completed)::\s*([^\]]*)\]")
GLYPH_RE = re.compile(r"^(?:[✅\U0001F534⏳\U0001F4C5⚠️]\s*)+")
STATUS_ORDER = {"blocked": 0, "open": 1, "done": 2}
GLYPH = {"blocked": "🔴", "open": "⏳", "done": "✅"}


class Item:
    __slots__ = ("desc", "status", "due", "raised", "owner", "src")

    def __init__(self, desc, status, due, raised, owner, src):
        self.desc, self.status, self.due = desc, status, due
        self.raised, self.owner, self.src = raised, owner, src

    def age(self, today: dt.date):
        if not self.raised:
            return None
        try:
            return (today - dt.date.fromisoformat(self.raised)).days
        except ValueError:
            return None


def owner_of(rel_path: str) -> tuple[str, bool]:
    """(owner label, is_calendar). Calendar notes are views, not real owners."""
    p = Path(rel_path)
    if "calendar" in p.parts:
        return f"day:{p.stem}", True
    return p.stem, False


def clean_desc(text: str) -> str:
    text = FIELD_RE.sub("", text)
    text = GLYPH_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" .")
    return text


def scan(today: dt.date) -> list[Item]:
    found: list[Item] = []
    for f in sorted(IDEAVERSE_DIR.rglob("*.md")):
        rel = f.relative_to(IDEAVERSE_DIR).as_posix()
        owner, _ = owner_of(rel)
        in_fence = False
        for line in f.read_text(encoding="utf-8").splitlines():
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue                       # ignore code examples
            line = CALLOUT_RE.sub("", line)    # unwrap callout items
            m = TASK_RE.match(line)
            if not m:
                continue
            fields = {k: v.strip() for k, v in FIELD_RE.findall(line)}
            if "status" not in fields:
                continue
            status = fields["status"].lower()
            if m.group(1).lower() == "x" and status != "done":
                status = "done"  # checked box wins
            found.append(Item(
                desc=clean_desc(m.group(2)),
                status=status,
                due=fields.get("due") or "",
                raised=fields.get("raised") or "",
                owner=fields.get("owner") or owner,
                src=rel,
            ))
    return dedupe(found)


def dedupe(items: list[Item]) -> list[Item]:
    """Same description in several notes → keep the one with a real (non-calendar) owner."""
    best: dict[str, Item] = {}
    for it in items:
        key = it.desc.lower()
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        cur_cal = cur.src.startswith("calendar/") or "calendar" in cur.src.split("/")
        it_cal = "calendar" in it.src.split("/")
        if cur_cal and not it_cal:
            best[key] = it  # prefer the owning (non-calendar) note
    return list(best.values())


def sort_key(it: Item, today: dt.date):
    age = it.age(today)
    due = it.due or "9999-99-99"
    return (STATUS_ORDER.get(it.status, 9), due, -(age if age is not None else -1))


def render(items: list[Item], today: dt.date, include_done: bool) -> str:
    shown = [i for i in items if include_done or i.status != "done"]
    shown.sort(key=lambda i: sort_key(i, today))
    counts = {s: sum(1 for i in items if i.status == s) for s in ("blocked", "open", "done")}

    out: list[str] = []
    out.append("---")
    out.append("generated: true")
    out.append(f"generated_on: {today.isoformat()}")
    out.append("tags: [open-items, ledger, generated]")
    out.append("---")
    out.append("")
    out.append("> [!warning] Generated file — do not edit by hand.")
    out.append(f"> Compiled by `{V.vault_rel('aiOS/scripts/open-items.py')}` from the "
               f"[[open_item]] lines in `{DATAVIEW_SOURCE}/`. "
               "Edit items in their owning note, then re-run.")
    out.append("")
    out.append("# Open items ledger")
    out.append("")
    out.append(f"_As of **{today.isoformat()}** — "
               f"🔴 {counts['blocked']} blocked · ⏳ {counts['open']} open"
               + (f" · ✅ {counts['done']} done" if include_done else "") + "._")
    out.append("")
    out.append("| | Item | Owner | Due | Age (d) |")
    out.append("|---|---|---|---|---|")
    for it in shown:
        age = it.age(today)
        age_s = "—" if age is None else (f"**{age}** ⚠️" if age >= 7 else str(age))
        due_s = it.due or "—"
        owner_link = f"[[{it.owner}]]" if not it.owner.startswith("day:") else it.owner
        out.append(f"| {GLYPH.get(it.status, '?')} | {it.desc} | {owner_link} | {due_s} | {age_s} |")
    out.append("")
    out.append("## Live view (Obsidian / Dataview)")
    out.append("")
    out.append("```dataview")
    out.append("TASK")
    out.append(f'FROM "{DATAVIEW_SOURCE}"')
    out.append("WHERE status = \"open\" OR status = \"blocked\"")
    out.append("SORT due ASC")
    out.append("GROUP BY status")
    out.append("```")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile the open-items ledger from the ideaVerse.")
    ap.add_argument("--today", help="ISO date to treat as today (for aging). Default: system date.")
    ap.add_argument("--check", action="store_true", help="Print to stdout; don't write. Exit 1 if it differs.")
    ap.add_argument("--include-done", action="store_true", help="Also list done items.")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    items = scan(today)
    text = render(items, today, args.include_done)

    if args.check:
        print(text)
        existing = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
        return 1 if existing != text else 0

    LEDGER.write_text(text, encoding="utf-8")
    n_open = sum(1 for i in items if i.status in ("open", "blocked"))
    print(f"✓ {LEDGER.relative_to(VAULT_DIR)} — {n_open} open/blocked item(s) from {len(items)} tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
