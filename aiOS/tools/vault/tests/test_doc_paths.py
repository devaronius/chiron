"""Every repo-root path named in `aiOS/` and `.claude/` prose must exist.

The cheap check a hand audit keeps missing. A sweep for stale *tooling* — scripts,
skills, config keys — does not catch a pointer at a missing *document*, because that
reads as prose rather than as a call.

Scope: `aiOS/**/*.md`, `.claude/**/*.md` and the repo's own instruction file — the
surface an agent reads and acts on. A vault path is *checked* when one of those files
names it, but the vault is not itself scanned: a note recording a fix must be free to
name a file precisely because it no longer exists. Code directories are skipped for the
same reason — a map may legitimately describe a package that has not landed yet.
"""
from __future__ import annotations

import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]

def _vault_prefix() -> str:
    """The vault directory as it appears in a path, from `aios.config.json`."""
    try:
        cfg = json.loads((REPO_ROOT / 'aiOS' / 'aios.config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'docs/'
    return '' if cfg.get('vaultAtRepoRoot') else f"{cfg.get('vaultDir', 'docs')}/"


#: Only root-anchored prefixes. A bare `open-items.py` in a runbook is relative to the
#: directory that runbook is talking about, and resolving those needs context this
#: check does not have.
PREFIXES = tuple(p for p in ('aiOS/', _vault_prefix(), '.claude/') if p)

#: `{vault}` in ALLOWED stands for the vault prefix, so a root-mode vault and a
#: `docs/` one both resolve the same entries.
_VAULT = _vault_prefix()

TOKEN = re.compile(r'`([^`\n]+)`')

#: Paths that are correctly absent, each with the reason. An entry here is a claim that
#: the reference is right and the file's absence is expected — not a way to silence a
#: failure. If you add one, say why.
ALLOWED = {
    # A multi-megabyte mermaid bundle, fetched on first use and gitignored.
    '.claude/skills/pdf-builder/.mermaid.min.js',
    # A harness convention: the directory appears with the repo's first command.
    '.claude/commands/',
}

#: Paths a tool *generates*. Absent before the first run and present after, so neither
#: state says anything about the prose that names them — and unlike an ALLOWED entry,
#: one of these is not dead once the file appears. Kept separate for exactly that
#: reason: the allowlist's own freshness check would otherwise fail the moment a
#: generator ran, which is the opposite of what it is for.
GENERATED = {
    '{vault}open-items.md',
    '{vault}vault-report.md',
}


def allowed() -> set[str]:
    """ALLOWED with `{vault}` resolved for this install's vault directory."""
    return {path.replace('{vault}', _VAULT) for path in ALLOWED}


def generated() -> set[str]:
    """GENERATED with `{vault}` resolved for this install's vault directory."""
    return {path.replace('{vault}', _VAULT) for path in GENERATED}


def documents():
    for pattern in ('aiOS/**/*.md', '.claude/**/*.md'):
        for path in REPO_ROOT.glob(pattern):
            if '__pycache__' not in path.parts:
                yield path
    # The repo's own instruction file, under whichever name this harness reads.
    for name in ('AGENTS.md', 'CLAUDE.md'):
        if (REPO_ROOT / name).is_file():
            yield REPO_ROOT / name


def referenced_paths(text: str):
    """Backticked tokens that are unambiguously repo-root paths."""
    for raw in TOKEN.findall(text):
        token = raw.strip()
        if not token or ' ' in token:
            continue
        # Globs, placeholders and shell fragments are patterns, not paths.
        if any(ch in token for ch in '*<>{}…|$()'):
            continue
        if not token.startswith(PREFIXES):
            continue
        # Trailing `:23` line numbers, `#anchors` and sentence punctuation.
        yield re.sub(r'[:#].*$', '', token).rstrip('.,;')


class TestReferencedPathsExist(unittest.TestCase):
    def test_no_prose_points_at_a_file_that_does_not_exist(self):
        missing = {}
        for doc in documents():
            for path in referenced_paths(doc.read_text(encoding='utf-8')):
                if path in allowed() or path in generated() or (REPO_ROOT / path).exists():
                    continue
                missing.setdefault(path, []).append(
                    str(doc.relative_to(REPO_ROOT)))

        self.assertEqual(missing, {}, '\n'.join(
            [''] + [f'  {p}  <- {", ".join(sorted(set(where)))}'
                    for p, where in sorted(missing.items())]))

    def test_the_check_has_something_to_check(self):
        # A regex that silently stops matching would make the test above pass by
        # finding nothing at all — the exact failure mode this whole file exists for.
        found = sum(len(list(referenced_paths(d.read_text(encoding='utf-8'))))
                    for d in documents())
        # A floor, not a census: the number grows with the project, and pinning it to
        # one vault's size turns every new note into a failing test somewhere else.
        self.assertGreater(found, 20, 'the extractor matched almost nothing')

    def test_allowlist_has_no_dead_entries(self):
        # An allowlisted path that now exists, or is no longer referenced anywhere, is
        # a claim nobody is checking. Drop it rather than leaving it to rot.
        referenced = set()
        for doc in documents():
            referenced.update(referenced_paths(doc.read_text(encoding='utf-8')))
        for path in sorted(allowed()):
            with self.subTest(path=path):
                self.assertIn(path, referenced,
                              'allowlisted but no longer referenced — remove it')
                self.assertFalse((REPO_ROOT / path).exists(),
                                 'allowlisted but now exists — remove it')


if __name__ == '__main__':
    unittest.main()
