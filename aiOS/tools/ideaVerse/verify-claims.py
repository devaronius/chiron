#!/usr/bin/env python3
"""Re-measure the things a document claims, and report the ones that have moved.

Most of what went stale across six review passes was re-derivable in one step: test
counts, page counts, diagram counts, a file size. Each was correct when written and
wrong when published, because nothing re-checked at publishing time.

Mark a measured value with the **name of a measurement**, not with a command:

    7 suites, 609 tests <!--verify: tests = 609-->
    38 pages            <!--verify: pdf-pages docs/.../note.pdf = 38-->

    verify-claims.py <file>…        check
    verify-claims.py --fix <file>   rewrite expectations to what measures now
    verify-claims.py --list         the measurements available

Exit 1 if any claim disagrees, so a hook or CI step can gate on it.

**Note text never names a program.** An earlier version ran the marker as a shell
command, which made any note body arbitrary execution — the Stop hook runs this
unattended, and research notes carry pasted clippings. Removing the shell was not
enough: `find -exec` and `git -c alias.x=!…` execute on their own, and a path
pattern admitted `../..`. Two allowlists failed in a row, so the tool no longer
takes a command at all. Each measurement below is implemented here; the only thing
a marker chooses is which one to call and, for some, a path inside the repo.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shlex
import subprocess
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

REPO_ROOT = V.REPO_ROOT

# How this repo runs its tests, for the `tests` and `suites` measurements — e.g.
# `"testCommand": "./.claude/run-tests.sh"` under `code` in aios.config.json. Unset means
# the two measurements are unavailable rather than wrong: a framework cannot guess a test
# runner, and a claim checked against the wrong command is worse than one left unchecked.
TEST_COMMAND = V.CONFIG["code"].get("testCommand", "")

CLAIM_RE = re.compile(r'<!--\s*verify:\s*(?P<body>.+?)\s*-->', re.S)

# Markers are not claims when they appear in code. The note that documents this
# syntax shows one as inline code; without this the tool measured its own
# documentation and failed the turn with no legitimate fix. All four markdown code
# forms, because pasted material arrives in whichever one its author used.
CODE_FORMS = (
    re.compile(r'^(?P<f>```+|~~~+).*?^(?P=f)\s*$', re.S | re.M),   # fenced
    re.compile(r'^(?: {4}|\t).*$', re.M),                          # indented
    re.compile(r'``.+?``', re.S),                                  # double span
    re.compile(r'`[^`\n]*`'),                                      # single span
)

TIMEOUT = 25        # under the Stop hook's 60s budget, so it can actually apply


def blank(match: re.Match) -> str:
    """Replace a match with spaces, preserving length so offsets still line up."""
    return re.sub(r'[^\n]', ' ', match.group(0))


def strip_code(text: str) -> str:
    for form in CODE_FORMS:
        text = form.sub(blank, text)
    return text


def repo_path(arg: str) -> pathlib.Path:
    """A path argument, resolved and required to stay inside the repo."""
    resolved = (REPO_ROOT / arg).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ValueError(f'{arg} resolves outside the repository')
    if not resolved.is_file():
        raise ValueError(f'{arg} is not a file')
    return resolved


def _run(argv: list[str]) -> str:
    """Fixed argv built here, never from note text."""
    done = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True,
                          text=True, timeout=TIMEOUT)
    return done.stdout


def m_tests(_: str) -> str:
    """Summed across suites — and only from a green run.

    A failing suite makes the runner echo its whole output, so `Ran N tests`
    appears twice for it and the total silently inflates. There is also no honest
    count to quote from a red run, so returning nothing is the right answer: the
    caller reports it as a failure rather than as agreement.
    """
    if not TEST_COMMAND:
        raise ValueError('no `code.testCommand` in aios.config.json — '
                         'the `tests` measurement has no runner to call')
    out = _run(shlex.split(TEST_COMMAND))
    if not re.search(r'all \d+ suites pass', out):
        return ''
    per_suite = re.findall(r'^\S+\s+Ran (\d+) tests', out, re.M)
    return str(sum(int(n) for n in per_suite))


def m_suites(_: str) -> str:
    if not TEST_COMMAND:
        raise ValueError('no `code.testCommand` in aios.config.json — '
                         'the `suites` measurement has no runner to call')
    found = re.search(r'all (\d+) suites pass', _run(shlex.split(TEST_COMMAND)))
    return found.group(1) if found else '0'


def m_vault_notes(_: str) -> str:
    found = re.search(r'(\d+) notes scanned',
                      _run(['python3', 'aiOS/tools/ideaVerse/vault-lint.py', '--quiet']))
    return found.group(1) if found else '0'


def m_wiki_sync(_: str) -> str:
    out = _run(['python3', 'aiOS/tools/wiki/wiki-sync.py'])
    return 'in sync' if 'Wiki is in sync' in out else 'drifted'


def m_pdf_pages(arg: str) -> str:
    raw = repo_path(arg).read_bytes()
    for opening, container in ((b'/Type /Page', b'/Type /Pages'),
                               (b'/Type/Page', b'/Type/Pages')):
        pages = raw.count(opening) - raw.count(container)
        if pages > 0:
            return str(pages)
    return '0'


def m_file_kb(arg: str) -> str:
    return str(repo_path(arg).stat().st_size // 1024)


def m_mermaid(arg: str) -> str:
    text = repo_path(arg).read_text(encoding='utf-8')
    return str(len(re.findall(r'^```mermaid', text, re.M)))


def m_sources(arg: str) -> str:
    text = repo_path(arg).read_text(encoding='utf-8')
    front = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not front:
        return '0'
    block = re.search(r'^sources:[ \t]*(.*)$', front.group(1), re.M)
    if not block:
        return '0'
    if block.group(1).strip().startswith('['):
        return str(len(re.findall(r'"[^"]*"|\'[^\']*\'', block.group(1))))
    tail = front.group(1)[block.end():]
    count = 0
    for line in tail.splitlines():
        if not line.strip():
            continue
        if not line.startswith((' ', '\t')) or not line.strip().startswith('- '):
            break
        count += 1
    return str(count)


MEASUREMENTS = {
    'tests':            (m_tests, '', 'total tests across every suite'),
    'suites':           (m_suites, '', 'passing suite count'),
    'vault-notes':      (m_vault_notes, '', 'notes vault-lint scans'),
    'wiki-sync':        (m_wiki_sync, '', '"in sync" or "drifted"'),
    'pdf-pages':        (m_pdf_pages, '<path>', 'pages in a rendered PDF'),
    'file-kb':          (m_file_kb, '<path>', 'file size in whole KB'),
    'mermaid-diagrams': (m_mermaid, '<path>', '```mermaid fences in a note'),
    'sources':          (m_sources, '<path>', 'entries in a note\'s `sources:`'),
}


def split_claim(body: str) -> tuple[str, str] | None:
    """`<measurement> [arg] = <expected>`, split at the last ` = `."""
    if ' = ' not in body:
        return None
    call, want = body.rsplit(' = ', 1)
    return call.strip(), want.strip()


def measure(call: str) -> tuple[bool, str]:
    parts = call.split()
    if not parts:
        return False, 'empty measurement'
    name, args = parts[0], parts[1:]
    if name not in MEASUREMENTS:
        return False, (f'`{name}` is not a measurement. Available: '
                       f'{", ".join(sorted(MEASUREMENTS))}')
    func, arity, _ = MEASUREMENTS[name]
    if arity and len(args) != 1:
        return False, f'`{name}` takes exactly one argument: {arity}'
    if not arity and args:
        return False, f'`{name}` takes no arguments'
    try:
        value = func(args[0] if args else '')
    except subprocess.TimeoutExpired:
        return False, f'timed out after {TIMEOUT}s'
    except (OSError, ValueError, zlib.error) as exc:
        return False, f'{exc.__class__.__name__}: {exc}'
    if value == '':
        return False, 'measured nothing — treat as a failure, not as agreement'
    return True, value


def check(path: pathlib.Path, fix: bool) -> tuple[int, int, str]:
    """(claims, mismatches, rewritten-text). Markers inside code are not claims."""
    text = path.read_text(encoding='utf-8')
    scannable = strip_code(text)
    claims = mismatches = 0
    out, last = [], 0
    for found in CLAIM_RE.finditer(scannable):
        parts = split_claim(text[found.start('body'):found.end('body')])
        if not parts:
            continue
        call, want = parts
        claims += 1
        ok, got = measure(call)
        if ok and got == want:
            print(f'  ok    {path.name}: {call} = {want}')
            continue
        mismatches += 1
        detail = got if ok else f'(did not measure — {got})'
        print(f'  STALE {path.name}: {call}\n          claimed {want!r}, now {detail!r}')
        if fix and ok:
            want_at = text.rindex(' = ', found.start('body'), found.end('body')) + 3
            out.append(text[last:want_at])
            out.append(got)
            last = found.end('body')
    out.append(text[last:])
    return claims, mismatches, ''.join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*')
    ap.add_argument('--fix', action='store_true',
                    help='rewrite each expectation to what measures now')
    ap.add_argument('--list', action='store_true', help='list the measurements')
    args = ap.parse_args()

    if args.list:
        for name, (_, arity, blurb) in sorted(MEASUREMENTS.items()):
            print(f'  {name} {arity}'.ljust(32) + blurb)
        return 0
    if not args.files:
        ap.error('give at least one file, or --list')

    total = stale = 0
    for name in args.files:
        path = pathlib.Path(name)
        if not path.exists():
            print(f'  ! no such file: {name}', file=sys.stderr)
            return 1
        claims, mismatches, rewritten = check(path, args.fix)
        total += claims
        stale += mismatches
        if args.fix and mismatches:
            path.write_text(rewritten, encoding='utf-8')
            print(f'  → rewrote {mismatches} expectation(s) in {path.name}')

    if not total:
        print('  no <!--verify: … = … --> claims found')
        return 0
    print(f'\n{total} claim(s), {stale} stale.'
          + ('' if stale else '  Everything still measures as written.'))
    return 1 if stale and not args.fix else 0


if __name__ == '__main__':
    raise SystemExit(main())
