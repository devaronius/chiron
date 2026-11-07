#!/usr/bin/env python3
"""
PreToolUse hook — enforce the Inspector's scope in the harness, not in prose.

The Inspector reviews other people's work and posts to their pull requests, so
two things must be true of it mechanically rather than by good intentions:

  * **It cannot change what the author ships.** No `Edit` tool is granted at all;
    this closes the shell route to the same thing — no `git commit`, no `push`,
    no `checkout` that would flip the branch a human is standing on. (It *may*
    mutate its own scratchpad worktree; see "On worktrees" below for why, and for
    what still holds.)
  * **It cannot reach a tracker except through the client the project configures**
    (`agents.inspector.scripts`). That client exposes no verb that casts a vote or
    moves a work item's state, which is how "the human keeps the sign-off" stops
    being a promise. Raw `curl` at the tracker's API would walk straight around it.

Scoped by `agent_type`, which PreToolUse carries for subagent calls and omits for
the main session — so nothing here constrains a human at the keyboard.

Two rules:
  Bash  — an ALLOWLIST of command heads, plus a per-subcommand allowlist for git.
          Arbitrary interpreters are refused, because `python3 -c "import
          urllib..."` reopens every endpoint the verb list closes. Named scripts
          are the exception, and only those that read: the configured tracker
          client, the vault reporters and the grader with their write flags
          refused, and `unittest discover` over one of the repo's own test
          directories.
  Write — the session scratchpad only. The findings file and working notes; never
          the repository, in any checkout of it.

On worktrees: the Inspector reviews a PR branch in a worktree it creates under the
scratchpad (`git worktree add`), never by checking out in place.

Note precisely what that means for writes, because it is easy to read the rule as
stronger than it is. `refuse_write` allows any path with a `scratchpad` segment, so
a write *into that worktree* is allowed — it is a checkout, but it is the agent's
own disposable one. This is deliberate rather than an oversight: reverting a hunk
and re-running the test is how the Inspector checks that a test would actually have
failed without the change (runbook Step 5b), and that is impossible if every
checkout is closed to it.

The guarantee that carries the weight is therefore not "it cannot write to a
checkout" but "no edit of its can reach the author's branch or the remote":
`commit`, `push`, `checkout`, `reset`, `rebase`, `merge` and `cherry-pick` are all
refused below, and the repository proper is closed because it has no `scratchpad`
segment. A worktree parked anywhere else is closed for the same reason.

Exit codes (PreToolUse contract):
  0 — allowed, or not our business
  2 — denied; stderr goes back to the agent so it can correct or report
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

AGENT = 'inspector'
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _config() -> dict:
    """`aios.config.json`, or an empty config if the aiOS is not installed here."""
    try:
        return json.loads(
            (REPO_ROOT / 'aiOS' / 'aios.config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


_AGENTS = (_config().get('agents') or {}).get(AGENT) or {}

# Read-only shell. Nothing here writes to the repo, the remote, or the board.
ALLOWED_HEADS = {
    'grep', 'egrep', 'fgrep', 'rg', 'find', 'ls', 'cat', 'head', 'tail', 'wc',
    'sort', 'uniq', 'cut', 'tr', 'jq', 'shasum', 'sha256sum', 'file', 'stat',
    'basename', 'dirname', 'echo', 'printf', 'true', 'diff', 'date', 'cd', 'pwd',
    'mktemp', 'awk', 'sed',
}

#: The toolchain the Inspector runs to turn opinions into facts — `agents.inspector.
#: buildCommands` in aios.config.json, e.g. ["flutter", "dart", "go", "npm"]. Empty by
#: default: a framework cannot know a project's build tool, and guessing one grants a
#: shell head nobody asked for. With none configured the Inspector can still read the
#: diff and run the aiOS suites; it reports that it could not run the project's own.
BUILD_HEADS = set(_AGENTS.get('buildCommands') or ())

# git subcommands that only read, plus `worktree` — which is how a PR branch gets
# reviewed without touching the checkout a human is working in. `checkout` and
# `switch` are absent on purpose: either would move someone's branch under them.
GIT_READONLY = {
    'fetch', 'diff', 'log', 'show', 'status', 'rev-parse', 'ls-remote', 'ls-files',
    'merge-base', 'blame', 'describe', 'cat-file', 'branch', 'remote', 'shortlog',
    'rev-list', 'name-rev', 'symbolic-ref', 'config', 'ls-tree',
}
# Global options that take a value, so the value is not mistaken for the subcommand.
# `-c key=value` is deliberately absent: a config override can run a command
# (`core.fsmonitor`, `diff.external`), so `git -c … diff` stays refused.
GIT_VALUE_OPTIONS = {'-C', '--git-dir', '--work-tree', '--namespace'}
GIT_WORKTREE_OK = {'add', 'list', 'remove', 'prune'}

# `python3` is allowed ONLY as a launcher for a named script — never `-c`, never a
# heredoc, never a module. Two kinds are named.
#
# The project's pull-request client, from `agents.inspector.scripts`. Its verb list is
# what keeps the sign-off with the human — the framework ships no such client, because
# a PR lives on a tracker chiron knows nothing about. With none configured, mode 2
# (review a pull request) is simply unavailable and the runbook says so.
SCRIPTS = tuple(_AGENTS.get('scripts') or ())
SCRIPT_RE = (re.compile(r'^python3?\s+\S*(?:' +
                        '|'.join(re.escape(s) for s in SCRIPTS) + r')\b')
             if SCRIPTS else None)

# The vault reporters. Without these a review of a docs change cannot reproduce the
# one class of evidence such a PR actually carries — lint state, wiki drift, whether
# a note is capture-ready — so the Inspector is left restating the author's own
# numbers back at them, which is not verification. `researcher-scope.py` already
# admits `research-capture.py` on the same reasoning.
#
# **Each maps to the flags it MAY be given, and every other `-…` word is refused.**
# This is an allowlist on purpose. Blocklisting the write flags was tried first and
# was not a boundary: argparse accepts `--u` for `--update`, and the shell hands the
# hook `--upd\atex` or `$(echo --update)` while argparse receives the real spelling.
# Enumerating what may be passed survives both, because an obfuscated flag is still
# an unrecognised `-…` word.
#
# **It is still not airtight, and the difference matters.** `segments()` does not
# split on `&` or `$(`, so `ls & python3 …/wiki-sync.py --update` is read as `ls` and
# the flag is never inspected. That route is pre-existing and tracked as #47470; this
# list closes the innocent and the abbreviated cases, not a determined one.
#
#   vault-lint.py   --fix     rewrites `created:` frontmatter
#   wiki-sync.py    --update  re-snapshots the drift baseline, which would let a
#                             reviewer silently bless the drift it was sent to find
# `research-capture.py` and `note-review.py` have no write verb at all.
READ_ONLY_FLAGS = {
    'aiOS/tools/vault/vault-lint.py': ('-q', '--quiet', '-c', '--categories'),
    'aiOS/tools/wiki/wiki-sync.py': ('-q', '--quiet'),
    'aiOS/tools/vault/research-capture.py': (),
    'aiOS/tools/vault/note-review.py': ('--json',),
    # No write path except `--fix`, which is absent from this list and therefore
    # refused. A reviewer is asked to reproduce a PR body's numbers; this is the
    # tool that measures them.
    'aiOS/tools/vault/verify-claims.py': (),
    # The aiOS invariants in the report's last section live nowhere else. Bare, it
    # rewrites vault-report.md, so `--stdout` is not just allowed but required.
    'aiOS/tools/vault/vault-report.py': ('--stdout',),
    # Reads a findings file and prints a verdict on it; it has no write path at all.
    'aiOS/tools/inspector/grading.py': ('--pr',),
}
ALWAYS_OK = ('-h', '--help')
# A reporter whose *default* is to write: allowed only with the flag that makes it print.
REQUIRED_FLAGS = {'aiOS/tools/vault/vault-report.py': '--stdout'}

# `python3 -m` is otherwise refused (`-m http.server`, `-m pip`), with one shape let
# through: unittest discovery over a test directory of this repo's own Python — the same
# thing `aiOS/tools/run-tests.sh` does per suite, which is already allowed. Running one
# suite is what lets a reviewer re-run the test a PR body names, or a guard check,
# without waiting on all of them. `-I` isolates the interpreter from the cwd and is
# harmless; `-t` would move the import root and is refused by not being matched.
UNITTEST_RE = re.compile(
    r'^python3?\s+(?:-I\s+)?-m\s+unittest\s+discover\s+-s\s+'
    r'\S*(?:\.claude/hooks/tests|\.claude/skills/[\w-]+/tests|aiOS/tools/[\w-]+/tests)/?'
    r'(?:\s+-p\s+[\w*.]+)?(?:\s+-v)?(?:\s+2>(?:&1|/dev/null))?\s*$')

# The repo's own test runner. A PR body's test counts are among the most-quoted and
# most-decayed numbers in it, and a reviewer who cannot run the suite can only repeat
# the author's figure — which is how "543 tests" survived two passes while the real
# number was 545. Matched by exact path, never a general shell: `bash`, `sh` and
# `./anything-else.sh` stay refused.
#
# Read-only by inspection: the runner only discovers `tests/` dirs and shells
# `python3 -m unittest`; the suites redirect every write at a temp git repo and mock
# the network (`.claude/hooks/tests/README.md`).
#
# Honest limit: discovery imports whatever `test_*.py` it finds, so inside a scratchpad
# worktree this is arbitrary execution. That is **not new** — `sed -i`, `awk` and
# `find -exec` already reach the same place from `ALLOWED_HEADS`, and closing the class
# properly is its own change. This does not make the posture worse; it does make the
# reviewer able to check a number they are otherwise asked to trust.
# `2>&1` and `2>/dev/null` are allowed: a failing run is unreadable without them and
# neither names a file. A `>` redirection to a path is deliberately not matched.
RUNNER_RE = re.compile(
    r'^(?:\./)?\S*aiOS/tools/run-tests\.sh(?:\s+-v|\s+--coverage)?'
    r'(?:\s+2>(?:&1|/dev/null))?\s*$')
REPORTER_RE = re.compile(
    r'^python3?\s+(\S*(?:' +
    '|'.join(re.escape(name) for name in READ_ONLY_FLAGS) +
    r'))\b(.*)$'
)

SEPARATORS = re.compile(r'\|\||&&|[;|\n]')
HEREDOC = re.compile(r'<<-?\s*[\'"]?(\w+)[\'"]?')
ENV_ASSIGN = re.compile(r'^\w+=')
QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')


def segments(command: str) -> list[str]:
    """Command heads, with heredoc bodies stripped so their text isn't parsed as code.

    Splitting is quote-aware: a `|` inside `jq '.[] | .key'` is an argument, not a
    pipe. Separators are located in a same-length masked copy, then sliced out of
    the original. Kept in step with researcher-scope.py deliberately — a parity
    test holds the two together rather than a shared import, because a PreToolUse
    hook must stay cheap to start.
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
        piece = piece.replace('$(', ' ').replace('`', ' ').strip()
        words = [w for w in piece.split() if not ENV_ASSIGN.match(w)]
        if words:
            out.append(' '.join(words))
    return out


def refuse_git(segment: str) -> str | None:
    words = segment.split()
    subs, skip = [], False
    for word in words[1:]:
        if skip:
            skip = False
        elif word in GIT_VALUE_OPTIONS:
            skip = True
        elif not word.startswith('-'):
            subs.append(word)
    if not subs:
        return None  # bare `git` / `git --version`
    sub = subs[0]
    if sub == 'worktree':
        action = subs[1] if len(subs) > 1 else ''
        if action not in GIT_WORKTREE_OK:
            return f'git worktree {action} — only {", ".join(sorted(GIT_WORKTREE_OK))}'
        if action == 'add' and 'scratchpad' not in segment:
            return ('git worktree add must target a path under your scratchpad — a '
                    'worktree inside the repo is still the repo')
        return None
    if sub not in GIT_READONLY:
        return (f'Review a PR branch with `git worktree add` under your scratchpad, and read '
                f'with the read-only verbs ({", ".join(sorted(GIT_READONLY))}). `git {sub}` is '
                'not one of them: commit, push, reset, rebase, merge, cherry-pick, stash and '
                '`checkout` change what you review, and `checkout` moves the branch a human '
                'is standing on.')
    return None


def refuse_python(segment: str) -> str | None:
    """None if this is a named script given only flags it is allowed to receive.

    Every `-…` word must be on that script's list. Refusing *unknown* flags rather
    than *known-bad* ones is what makes an abbreviation, a backslash-escaped spelling
    and a `$(…)` substitution all unrecognised here, where a blocklist of exact
    spellings waved each of them through.

    Not a complete boundary: a command the splitter never reaches — anything after an
    unsplit `&` or inside `$(…)` — is not inspected at all. Tracked as #47470.
    """
    segment = segment.replace('"', '').replace("'", '')
    if (SCRIPT_RE is not None and SCRIPT_RE.match(segment)) or UNITTEST_RE.match(segment):
        return None
    found = REPORTER_RE.match(segment)
    if not found:
        named = ', '.join(SCRIPTS) if SCRIPTS else 'nothing (no pull-request client ' \
                                                   'is configured for this repo)'
        return (f'Launch {named}, one of the read-only reporters '
                '(' + ', '.join(sorted(READ_ONLY_FLAGS)) + '), or '
                '`-m unittest discover -s <a tests/ dir of this repo>`; this command is '
                'none of them. Use jq / wc / sort / uniq for computation.')
    script = next(n for n in READ_ONLY_FLAGS if found.group(1).endswith(n))
    allowed = READ_ONLY_FLAGS[script] + ALWAYS_OK
    words = found.group(2).split()
    required = REQUIRED_FLAGS.get(script)
    if required and required not in words:
        return (f'Run {script} with `{required}`: without it the script writes its report '
                'into the vault. You measure the vault; you do not change it.')
    for word in words:
        if not word.startswith('-') or word == '-':
            continue                                    # a positional: a path or a term
        if word.split('=', 1)[0] in allowed:
            continue
        return (f'Give {script} only {", ".join(allowed) or "positional arguments"} — '
                f'`{word}` is not one of them. The write flags are excluded by being '
                'absent from that list, so an abbreviation or a shell substitution does '
                'not reach them either. You measure the vault; you do not change it.')
    return None


def refuse_bash(command: str) -> str | None:
    if HEREDOC.search(command):
        return ('Run the command inline, not as a heredoc — a heredoc smuggles an '
                'interpreter past the allowlist.')
    for segment in segments(command):
        words = segment.split()
        head = words[0]
        if head in ('python', 'python3'):
            reason = refuse_python(segment)
            if reason:
                return reason
            continue
        if head == 'git':
            reason = refuse_git(segment)
            if reason:
                return reason
            continue
        if head == 'curl':
            return ('Reach a tracker through the configured client '
                    f'({", ".join(SCRIPTS) or "none configured"}), which exposes no verb '
                    'that votes or moves a work item — that is what keeps the sign-off '
                    'with the human. curl could do both.')
        if RUNNER_RE.match(segment):
            continue
        if head in BUILD_HEADS or head in ALLOWED_HEADS:
            continue
        return (f'Use a command on the Inspector allowlist; `{head}` is not on it. Reach '
                f'a tracker through the configured client ({", ".join(SCRIPTS) or "none configured"}), '
                'and never modify what you review. If the task genuinely needs this, '
                'stop and report it instead of working around it.')
    return None


def refuse_write(path: str) -> str | None:
    if not path:
        return 'no file_path'
    target = pathlib.Path(path).expanduser()
    # Matched as a path SEGMENT rather than a substring, so a checkout that happens
    # to live under a directory of that name does not switch the whole scope off.
    if 'scratchpad' in target.parts:
        return None
    return (f'Write to your scratchpad; {path} is outside it. The Inspector never writes '
            'code (you review it, you do not change it), docs/ or .claude/. Report the '
            'finding; someone else makes the change.')


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
        print(f'Refused by the Inspector scope: {reason}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
