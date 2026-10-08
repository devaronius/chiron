#!/usr/bin/env python3
"""
open-items — scan the ideaVerse for open items and compile the open-items ledger.

An *open item* (see ideaVerse/atlas/concepts/open_item.md) is a Markdown task
line carrying Dataview inline fields, e.g.:

    - [ ] Wire the export endpoint [status:: open] [assignee:: agent] [due:: 2026-07-31]

`assignee::` is *who must act next*, and the only thing that routes an item to a lane
(see the concept note): `agent`, the handle in aios.config.json `assignees.self`, any
other name, or absent. `blocked` outranks the lane, because unblocking is a human act.

This script walks ideaVerse/, finds every line with a `[status:: …]` field,
computes each item's age from `raised::`, de-duplicates items that appear in more
than one note (preferring a real owner over a time-boxed calendar view), and writes
a single ledger view to open-items.md — a static Markdown table (durable
everywhere) plus a Dataview block (live in Obsidian). It is a *view generator*;
the source of truth stays in the owning effort/project notes.

Kept separate from wiki-sync.py on purpose: that script detects wiki drift, this one
compiles a task view — different jobs, different outputs.

Usage:
  python3 aiOS/tools/ideaVerse/open-items.py                 # write open-items.md
  python3 aiOS/tools/ideaVerse/open-items.py --today 2026-07-08   # pin "today" (aging)
  python3 aiOS/tools/ideaVerse/open-items.py --check         # print, don't write (exit 1 if changed)
  python3 aiOS/tools/ideaVerse/open-items.py --include-done   # also list done items
  python3 aiOS/tools/ideaVerse/open-items.py --lane           # ripe items owed a disposition
  python3 aiOS/tools/ideaVerse/open-items.py --lane --all     # the whole human lane
  python3 aiOS/tools/ideaVerse/open-items.py --lane --json    # the same, for a hook or the queue
  python3 aiOS/tools/ideaVerse/open-items.py --lane agent --json   # the agent queue's input
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

# Layout comes from vault_lib — one definition of where the vault is, so a move like
# aiOS/ going to the repo root is a one-file change rather than a hunt.
VAULT_DIR = V.VAULT_DIR
IDEAVERSE_DIR = V.IDEAVERSE_DIR
LEDGER = VAULT_DIR / "open-items.md"

# Dataview resolves FROM against the Obsidian vault root, which is the repo root — so the
# source path carries the vault directory unless the vault IS the repo root.
DATAVIEW_SOURCE = V.vault_rel("ideaVerse")

CALLOUT_RE = re.compile(r"^\s*(?:>\s?)+")            # strip callout '>' prefixes
FENCE_RE = re.compile(r"^\s*(?:>\s?)*```")           # code-fence toggle
TASK_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.*)$")
FIELD_RE = re.compile(r"\[(status|due|raised|owner|assignee|completed)::\s*([^\]]*)\]")
GLYPH_RE = re.compile(r"^(?:[✅\U0001F534⏳\U0001F4C5⚠️]\s*)+")
GLYPH = {"blocked": "🔴", "open": "⏳", "done": "✅"}

# `agent` is a reserved literal, deliberately not configurable — the routing table names
# it directly, and a vault that could rename it would need every runbook reworded too.
AGENT = "agent"
SELF = str(V.CONFIG["assignees"].get("self", "")).strip().lower()

# Sorts after every real ISO date, so undated items fall to the end of a due-ordered list.
NO_DUE = "9999-12-31"


class Item:
    __slots__ = ("desc", "status", "due", "raised", "owner", "assignee", "src")

    def __init__(self, desc, status, due, raised, owner, src, assignee=""):
        self.desc, self.status, self.due = desc, status, due
        self.raised, self.owner, self.src = raised, owner, src
        self.assignee = assignee

    def age(self, today: dt.date):
        if not self.raised:
            return None
        try:
            return (today - dt.date.fromisoformat(self.raised)).days
        except ValueError:
            return None

    def due_date(self):
        try:
            return dt.date.fromisoformat(self.due) if self.due else None
        except ValueError:
            return None            # a malformed date is treated as no date, not a crash

    def due_malformed(self) -> bool:
        """A `due::` that is present but unreadable — a typo, not an absent date.

        The two must stay distinguishable, because `due_date()` collapses them to None
        and the queue reads None as *ready now*. `[due:: 2026-10-32]` is a plausible
        slip, and without this it makes the queue run today the item somebody
        deliberately deferred to next week — walking straight around the regression
        test that parks a future-dated agent item.
        """
        if not self.due:
            return False
        try:
            dt.date.fromisoformat(self.due)
        except ValueError:
            return True
        return False


def lane_of(it: Item) -> str:
    """Which lane an item routes to: mine · agent · other · unrouted (· done).

    `blocked` outranks the assignee on purpose: unblocking is a human act, so a blocked
    item is the human's to act on whoever it is assigned to. Absence is never read as
    `agent` — an agent must not infer it may start work nobody delegated.
    """
    if it.status == "done":
        return "done"
    if it.status == "blocked":
        return "mine"
    who = it.assignee.strip().lower()
    if not who:
        return "unrouted"
    if who == AGENT:
        return "agent"
    if SELF and who == SELF:
        return "mine"
    return "other"


def is_ripe(it: Item, today: dt.date) -> bool:
    """Ripe = a disposition is owed today. Unrouted always is; otherwise due today or past.

    An undated item is deliberately never ripe — that is what keeps the session-start
    prompt short enough to answer instead of scroll past.
    """
    if lane_of(it) == "unrouted":
        return True
    if it.due_malformed():
        # A repair owed, not a quiet park — but never in the `other` lane, which stays
        # silent whatever is wrong with the item. It is not yours to fix.
        return lane_of(it) != "other"
    due = it.due_date()
    return due is not None and due <= today


def is_ready(it: Item, today: dt.date) -> bool:
    """Agent lane: may the queue pick this up now?

    Deliberately *not* is_ripe(). For a human, an undated item is not ripe — nagging
    about it every session is what turns the prompt into wallpaper. For the queue an
    undated item is ready immediately; what parks it is a future `due::`, because that
    is the ask-again date for every lane, not only the human's. Without this, a
    re-check deliberately deferred to next week is executed the day it is written.

    The two predicates disagree in *opposite* directions on an unreadable `due::`, and
    both deliberately: the human is shown it so the typo gets fixed, the queue refuses
    it so a slip of the keyboard can never be what authorises unattended work.
    """
    if it.due_malformed():
        return False
    due = it.due_date()
    return due is None or due <= today


def is_view(rel_path: str) -> bool:
    """A time-boxed calendar note mentions items that belong somewhere else.

    Days, briefings, meetings and sprints are views. `calendar/research/` is not:
    a research note is the durable origin of the items it raises, and nothing
    else carries them until they are distilled into an atlas note.
    """
    parts = Path(rel_path).parts
    return "calendar" in parts and "research" not in parts


def owner_of(rel_path: str) -> tuple[str, bool]:
    """(owner label, is_view). Views are printed unlinked and lose a dedupe tie."""
    p = Path(rel_path)
    if is_view(rel_path):
        return f"day:{p.stem}", True
    return p.stem, False


# Derived from the description, never new inline fields. open_item.md rules a `ticket::`
# field out: the mapping is one line of prose and a field buys nothing the description
# does not already carry. (It used to be justified by this file being chiron-vendored
# and liable to upgrade conflicts — `aiOS/` forked and is no longer installer-managed,
# so that cost is gone and the rule rests on the field being unnecessary.) Parsing the
# `Tracked as [#NNNNN](url)` convention that already exists adds no syntax at all.
#
# They exist because the agent queue's three eligibility gates — a code item needs a
# ticket, a denied deliverable is not eligible, code items are capped — were all stated
# as rules for the agent to apply by reading prose about its own job. The first
# supervised run (2026-10-02) found nothing in `--json` to apply them to. That is the
# same shape as the failure which put the denylist pre-check in the schedule: two items
# were picked up, worked, refused at the guard and handed back, every run, unnoticed.
TICKET_RE = re.compile(r"Tracked as \[#(\d+)\]")
BACKTICKED = re.compile(r"`([^`\n]+)`")
# Conservative on purpose, and conservative in the safe direction: a token that is not a
# path costs a denylist lookup that misses, while a path that is not recognised costs
# the pre-check. Rejects `_intlSystemNotBuilt` (no dot, no slash) and `'…'.t(`
# (characters a path cannot hold).
PATHISH = re.compile(r"^[A-Za-z0-9._*/-]+$")


def ticket_of(desc: str) -> str:
    m = TICKET_RE.search(desc)
    return m.group(1) if m else ""


def paths_in(desc: str) -> list[str]:
    """Repo-relative paths the item's description names, in order, de-duplicated."""
    out: list[str] = []
    for token in BACKTICKED.findall(desc):
        t = token.strip().rstrip(",;:.")
        if PATHISH.match(t) and ("/" in t or "." in t) and t not in out:
            out.append(t)
    return out


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
                assignee=fields.get("assignee") or "",
                src=rel,
            ))
    return dedupe(found)


def dedupe(items: list[Item]) -> list[Item]:
    """Same description in several notes → keep the one with a real owner."""
    best: dict[str, Item] = {}
    for it in items:
        key = it.desc.lower()
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        if is_view(cur.src) and not is_view(it.src):
            best[key] = it  # prefer the owning note over a view
    return list(best.values())


def sort_key(it: Item, today: dt.date):
    """The one ordering rule, used by every view: blocked-and-ripe → overdue → due
    soonest → oldest `raised::`. Declared priority stays deliberately out of the schema,
    so this derivation is the only thing that says what to look at first."""
    age = it.age(today)
    return (
        1 if it.status == "done" else 0,          # done last, when shown at all
        0 if (it.status == "blocked" and is_ripe(it, today)) else 1,
        it.due or NO_DUE,
        -(age if age is not None else -1),
    )


def render(items: list[Item], today: dt.date, include_done: bool) -> str:
    shown = [i for i in items if include_done or i.status != "done"]
    shown.sort(key=lambda i: sort_key(i, today))
    counts = {s: sum(1 for i in items if i.status == s) for s in ("blocked", "open", "done")}
    unrouted = sum(1 for i in items if lane_of(i) == "unrouted")

    out: list[str] = []
    out.append("---")
    out.append("generated: true")
    out.append(f"generated_on: {today.isoformat()}")
    out.append("tags: [open-items, ledger, generated]")
    out.append("---")
    out.append("")
    out.append("> [!warning] Generated file — do not edit by hand.")
    out.append("> Compiled by `aiOS/tools/ideaVerse/open-items.py` from the "
               f"[[open_item]] lines in `{DATAVIEW_SOURCE}/`. "
               "Edit items in their owning note, then re-run.")
    out.append("")
    out.append("# Open items ledger")
    out.append("")
    out.append(f"_As of **{today.isoformat()}** — "
               f"🔴 {counts['blocked']} blocked · ⏳ {counts['open']} open"
               + (f" · 🧭 {unrouted} unrouted" if unrouted else "")
               + (f" · ✅ {counts['done']} done" if include_done else "") + "._")
    out.append("")
    out.append("| | Item | Owner | Assignee | Due | Age (d) |")
    out.append("|---|---|---|---|---|---|")
    for it in shown:
        age = it.age(today)
        age_s = "—" if age is None else (f"**{age}** ⚠️" if age >= 7 else str(age))
        due_s = it.due or "—"
        owner_link = f"[[{it.owner}]]" if not it.owner.startswith("day:") else it.owner
        who = it.assignee or "—"
        out.append(f"| {GLYPH.get(it.status, '?')} | {it.desc} | {owner_link} | {who} | {due_s} | {age_s} |")
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


def why_ripe(it: Item, today: dt.date) -> str:
    """The one-line reason a disposition is owed — what you answer against."""
    if lane_of(it) == "unrouted":
        return "unrouted — needs an assignee"
    if it.due_malformed():
        return f"unreadable due date (`{it.due}`) — fix it"
    due = it.due_date()
    if due is None:
        return ""
    days = (today - due).days
    if days > 0:
        return f"overdue {days}d (due {it.due})"
    if days == 0:
        return f"due today ({it.due})"
    return f"due in {-days}d ({it.due})"


def lane_items(items, lane: str, today: dt.date, show_all: bool):
    """Items in one lane, in derived order. Without --all, only the ripe ones."""
    picked = [i for i in items if lane_of(i) == lane]
    if not show_all:
        ready = is_ready if lane == "agent" else is_ripe
        picked = [i for i in picked if ready(i, today)]
    picked.sort(key=lambda i: sort_key(i, today))
    return picked


def malformed_due_items(items):
    """Items whose `due::` is present but unreadable, in any lane.

    Reported across lanes rather than inside one, because an unreadable date makes an
    item fall out of *both*: the agent lane draws on is_ready, which now refuses it, and
    the human lane only ever shows `mine` and `unrouted`. Without this it would be
    refused by the queue and invisible to everyone — the quietest possible failure.
    """
    return [i for i in items if i.status != "done" and i.due_malformed()]


def render_lane(items, lane: str, today: dt.date, show_all: bool) -> str:
    """The session-start digest. Ripe items only by default — a prompt that fires on
    every item every session becomes wallpaper, and then nobody answers it."""
    if lane == "mine":
        shown = lane_items(items, "mine", today, show_all) + \
                lane_items(items, "unrouted", today, show_all)
        shown.sort(key=lambda i: sort_key(i, today))
        parked = sum(1 for i in items
                     if lane_of(i) in ("mine", "unrouted") and not is_ripe(i, today))
    elif lane == "agent":
        shown = lane_items(items, "agent", today, show_all)
        parked = sum(1 for i in items
                     if lane_of(i) == "agent" and not is_ready(i, today))
    else:
        shown = lane_items(items, lane, today, show_all)
        parked = 0

    # Only the human's digest carries the lint, and only for items it is not already
    # listing. Emitting it everywhere printed a ripe `mine` item twice — once numbered,
    # once as a warning — and made `--lane other` speak at all, which the lane rules say
    # it must never do: that lane is silent unless the item is asked for by name.
    broken = [i for i in malformed_due_items(items)
              if lane == "mine" and i not in shown]

    if not shown and not parked and not broken:
        return ""

    if show_all:
        head = f"🧭 {len(shown)} item(s)"
    else:
        head = f"🧭 {len(shown)} " + ("ready" if lane == "agent" else "ripe")
    if parked and not show_all:
        head += f" · {parked} parked"
    out = [head]
    for n, it in enumerate(shown, 1):
        reason = why_ripe(it, today)
        out.append(f"  {n}. {it.desc}" + (f" — {reason}" if reason else ""))
    if lane == "mine" and parked and not show_all:
        out.append('  → "what should we do today" for the full lane')
    for it in broken:
        out.append(f"  ⚠️  unreadable due date (`{it.due}`) — {it.desc} [{it.src}]")
    return "\n".join(out)


def lane_json(items, lane: str, today: dt.date, show_all: bool) -> str:
    """The machine surface. Nothing ever regex-parses the rendered ledger — a consumer
    that wants item data adds a flag here instead."""
    if lane == "mine":
        picked = lane_items(items, "mine", today, show_all) + \
                 lane_items(items, "unrouted", today, show_all)
        picked.sort(key=lambda i: sort_key(i, today))
    else:
        picked = lane_items(items, lane, today, show_all)
    return json.dumps({
        "today": today.isoformat(),
        "lane": lane,
        "items": [{
            "desc": i.desc, "status": i.status, "assignee": i.assignee,
            "owner": i.owner, "due": i.due, "raised": i.raised,
            "age": i.age(today), "ripe": is_ripe(i, today),
            "ready": is_ready(i, today),
            "why": why_ripe(i, today), "src": i.src,
            "ticket": ticket_of(i.desc), "paths": paths_in(i.desc),
        } for i in picked],
    }, ensure_ascii=False, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile the open-items ledger from the ideaVerse.")
    ap.add_argument("--today", help="ISO date to treat as today (for aging). Default: system date.")
    ap.add_argument("--check", action="store_true", help="Print to stdout; don't write. Exit 1 if it differs.")
    ap.add_argument("--include-done", action="store_true", help="Also list done items.")
    ap.add_argument("--lane", nargs="?", const="mine",
                    choices=["mine", "agent", "other", "unrouted"],
                    help="Print one lane instead of writing the ledger. Default: mine.")
    ap.add_argument("--all", action="store_true",
                    help="With --lane: the whole lane, not only the ripe items.")
    ap.add_argument("--json", action="store_true", help="With --lane: emit JSON.")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    items = scan(today)

    if args.lane:
        if args.json:
            print(lane_json(items, args.lane, today, args.all))
        else:
            text = render_lane(items, args.lane, today, args.all)
            if text:
                print(text)
        return 0

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
