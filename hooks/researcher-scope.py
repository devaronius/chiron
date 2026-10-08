#!/usr/bin/env python3
"""
PreToolUse hook — enforce the researcher agent's write scope in the harness, not in prose.

The Researcher runs unattended, so its constitution is documentation, not a boundary:
the first live run of this pattern reached the remote through its publish command because
it was told to, while raw `git push` sat one Bash call away the whole time. This closes that.

Scoped by `agent_type`, which PreToolUse carries for subagent calls and omits for the
main session — so nothing here constrains a human at the keyboard.

Two rules:
  Bash  — an ALLOWLIST of command heads. Arbitrary interpreters are refused, because
          `python3 -c "import subprocess..."` reopens everything the list closes.
  Write — paths under docs/ideaVerse/ or a scratchpad only, and never a map's work note.
          `publish` refuses to *commit* the same set; this stops it being written at all.

Exit codes (PreToolUse contract):
  0 — allowed, or not our business
  2 — denied; stderr goes back to the agent so it can correct or report
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

AGENT = 'researcher'
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _config() -> dict:
    """`aios.config.json`, or an empty config if the aiOS is not installed here."""
    try:
        return json.loads(
            (REPO_ROOT / 'aiOS' / 'aios.config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


CONFIG = _config()
_AGENTS = (CONFIG.get('agents') or {}).get(AGENT) or {}

#: Where the notes live, from config rather than assumed: a hook that guards the wrong
#: directory is worse than none, because it reads as protection.
VAULT = ('ideaVerse/' if CONFIG.get('vaultAtRepoRoot')
         else f"{CONFIG.get('vaultDir', 'docs')}/ideaVerse/")

#: Vault paths this agent may not write even though they are inside the vault — the
#: notes some other session owns exclusively. Repo-relative prefixes, from
#: `agents.researcher.protectedPaths`. Empty by default: a project declares its own.
PROTECTED = tuple(_AGENTS.get('protectedPaths') or ())

# Command heads the Researcher may run. Everything else is refused by default.
# Read-only by construction: nothing here writes to the repo, the remote, or the board
# except the two scripts, which enforce their own scope.
ALLOWED_HEADS = {
    'grep', 'egrep', 'fgrep', 'rg', 'find', 'ls', 'cat', 'head', 'tail', 'wc',
    'sort', 'uniq', 'cut', 'tr', 'jq', 'shasum', 'sha256sum', 'file', 'stat',
    'basename', 'dirname', 'echo', 'printf', 'true', 'gzip', 'date', 'cd', 'pwd',
}

# `python3` is allowed ONLY as a launcher for a named script — never `-c`, never a
# heredoc, never a module. `research-capture.py` always, because validating the note
# before publishing it is the job; anything else the project binds in
# `agents.researcher.scripts` (its tracker client, typically), which is how an
# unattended run reaches a board at all without a general interpreter.
SCRIPTS = ('aiOS/tools/ideaVerse/research-capture.py',
           *(_AGENTS.get('scripts') or ()))
SCRIPT_RE = re.compile(
    r'^python3?\s+\S*(?:' + '|'.join(re.escape(s) for s in SCRIPTS) + r')\b')

#: Hosts a read-only `curl` may reach, from `agents.researcher.curlHosts`. Empty by
#: default, which refuses `curl` outright — a probe is a capability a project grants
#: deliberately, never one an agent inherits from the framework.
CURL_HOSTS = tuple(_AGENTS.get('curlHosts') or ())
CURL_WRITE_FLAGS = (' -X ', ' -d ', ' -T ', ' --data', ' --upload', ' --form', ' -F ')

# Splits a command line into the pieces that each start a new program.
SEPARATORS = re.compile(r'\|\||&&|[;|\n]')
HEREDOC = re.compile(r'<<-?\s*[\'"]?(\w+)[\'"]?')
ENV_ASSIGN = re.compile(r'^\w+=')
QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')


def segments(command: str) -> list[str]:
    """Command heads, with heredoc bodies stripped so their text isn't parsed as code.

    Splitting is quote-aware: a `|` inside `jq '.[] | .key'` is an argument, not a
    pipe, and treating it as one refused a legitimate command on the first test run.
    Separators are located in a same-length masked copy, then sliced out of the original.
    """
    heredoc = HEREDOC.search(command)
    if heredoc:
        command = command[:heredoc.start()]
    masked = QUOTED.sub(lambda m: 'Q' * len(m.group(0)), command)

    pieces, last = [], 0
    for found in SEPARATORS.finditer(masked):
        pieces.append(command[last:found.start()])
        last = found.end()
    pieces.append(command[last:])

    out = []
    for piece in pieces:
        # `$(...)` and backticks would smuggle a second command through; treat as code.
        piece = piece.replace('$(', ' ').replace('`', ' ').strip()
        words = [w for w in piece.split() if not ENV_ASSIGN.match(w)]
        if words:
            out.append(' '.join(words))
    return out


def refuse_bash(command: str) -> str | None:
    if HEREDOC.search(command):
        return 'heredocs are refused — they smuggle an interpreter past the allowlist'
    for segment in segments(command):
        head = segment.split()[0]
        if SCRIPT_RE.match(segment):
            continue
        if head in ('python', 'python3'):
            return (f'`{segment.split()[0]} {segment.split()[1] if len(segment.split()) > 1 else ""}`'
                    f' — python3 may only launch: {", ".join(SCRIPTS)}. '
                    'Use jq / wc / shasum / sort / uniq for computation.')
        if head == 'curl':
            if not CURL_HOSTS:
                return ('curl is refused — no `agents.researcher.curlHosts` is '
                        'configured, so this vault grants no probe target')
            if not any(h in segment for h in CURL_HOSTS):
                return f'curl is limited to {", ".join(CURL_HOSTS)}'
            if any(flag in f' {segment} ' for flag in CURL_WRITE_FLAGS):
                return 'curl is read-only here — no -X, -d, -T, --data, --form or --upload'
            continue
        if head not in ALLOWED_HEADS:
            return (f'`{head}` is not on the Researcher allowlist. You reach the remote and '
                    'the tracker only through the scripts named above — never raw git, gh '
                    'or a vendor CLI. If the task genuinely needs this, stop and report it '
                    'instead of working around it.')
    return None


def is_protected(rel: pathlib.Path) -> bool:
    """A vault path some other session owns exclusively.

    Configured per project (`agents.researcher.protectedPaths`), because which notes are
    single-writer is a project's convention, not the framework's: typically the note a
    long-running effort's own session edits every turn, where two writers collide.
    Prefix match on the repo-relative path — a directory prefix covers its tree.
    """
    return any(str(rel).startswith(prefix) for prefix in PROTECTED)


def refuse_write(path: str) -> str | None:
    if not path:
        return 'no file_path'
    text = str(path)
    # Resolved against the repo root, not the cwd: a hook is invoked from the project
    # directory today, but a relative path must not mean different things by caller.
    given = pathlib.Path(text)
    target = (given if given.is_absolute() else REPO_ROOT / given).resolve()
    try:
        rel = target.relative_to(REPO_ROOT)
    except ValueError:
        # Outside the repo the session scratchpad is the only sanctioned target. Matched
        # as a path SEGMENT rather than a substring, so a checkout that happens to live
        # under a directory of that name does not switch the whole scope off.
        if 'scratchpad' in target.parts:
            return None
        return f'{text} is outside the repository and not in a scratchpad'
    if not str(rel).startswith(VAULT):
        return (f'{rel} — you may write your one note under {VAULT}, and nothing else: '
                'not a protected note, not the compiled wiki, not code, not the '
                'harness config directory.')
    if is_protected(rel):
        return (f'{rel} is owned exclusively by another session (it matches '
                '`agents.researcher.protectedPaths`). Write your findings in your own '
                'note; handing them on is the dispatcher\'s step, not a write of yours.')
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get('agent_type') != AGENT:
        return 0

    tool = payload.get('tool_name')
    supplied = payload.get('tool_input') or {}

    if tool == 'Bash':
        reason = refuse_bash(supplied.get('command', ''))
    elif tool in ('Write', 'Edit', 'NotebookEdit'):
        reason = refuse_write(supplied.get('file_path', ''))
    else:
        return 0

    if reason:
        print(f'Refused by the Researcher scope: {reason}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
