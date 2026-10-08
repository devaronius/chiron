#!/usr/bin/env python3
"""
SessionStart hook — put the ripe open items in front of the human, every session.

The lanes design (the vault's `open_item` concept note) routes each open item by its
`[assignee::]` field. This hook surfaces one lane: the human's, and only the items
that are *ripe* — overdue, due today, or unrouted. Parked items are counted, not listed.
A digest that fires on every item every session becomes wallpaper, and then nobody
answers it; the whole mechanism dies quietly.

A hook rather than a line in the project's instruction file on purpose: an instruction is
advisory, and you never learn which sessions skipped it. The *policy* — what a disposition
is, what to write back — stays in that file, because it is judgment a hook cannot do.

Exit codes (SessionStart contract):
  0 — always. A ledger problem must never block a session from starting; the worst
      case is a session with no digest, which is exactly today's behaviour.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "aiOS" / "tools" / "ideaVerse" / "open-items.py"
TIMEOUT = 20


def main() -> int:
    if not SCANNER.exists():
        return 0
    try:
        result = subprocess.run(
            [sys.executable, str(SCANNER), "--lane"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return 0           # never block a session on the ledger

    digest = result.stdout.strip()
    if result.returncode != 0 or not digest:
        return 0           # nothing ripe, nothing parked — say nothing

    print(
        "Open items owed a disposition — each needs one from you: start it, defer it "
        "with a reason, or reassign it.\n\n" + digest
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
