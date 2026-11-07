"""The inspector's non-negotiables live in two files, and must say the same thing.

The runbook (`aiOS/runbooks/inspector.runbook.md`) is the source of truth for behaviour;
the harness adapter (`.claude/agents/inspector.md`) is the copy the agent is guaranteed to
read. Each non-negotiable carries an `<!-- nn:slug -->` marker in both, and this checks
the two sets match. The adapter is seeded, so a consumer may edit it — which is exactly
when a rule can fall out of it unnoticed.
"""
from __future__ import annotations

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[4]
RUNBOOK = REPO / 'aiOS' / 'runbooks' / 'inspector.runbook.md'
ADAPTER = REPO / '.claude' / 'agents' / 'inspector.md'
SLUG = re.compile(r'<!--\s*nn:([a-z0-9-]+)\s*-->')
NUMBERED = re.compile(r'^(\d+)\.\s', re.M)


def slugs(path: pathlib.Path) -> list[str]:
    return SLUG.findall(path.read_text(encoding='utf-8'))


class TestNonNegotiableParity(unittest.TestCase):
    def setUp(self):
        if not ADAPTER.is_file():
            self.skipTest('no .claude/agents/inspector.md — the Claude adapter is not installed')

    def test_every_runbook_non_negotiable_carries_exactly_one_slug(self):
        # Without this the parity check is opt-in: an unslugged rule is in neither set,
        # so adding one to the runbook alone passes every other assertion here.
        text = RUNBOOK.read_text(encoding='utf-8')
        start = text.index('## Non-negotiables')
        section = text[start:text.index('\n## ', start + 1)]
        bounds = [m.start() for m in NUMBERED.finditer(section)] + [len(section)]
        items = [section[a:b] for a, b in zip(bounds, bounds[1:])]
        self.assertGreaterEqual(len(items), 7)
        for item in items:
            with self.subTest(rule=item.splitlines()[0][:60]):
                self.assertEqual(len(SLUG.findall(item)), 1)

    def test_no_duplicate_slugs_in_either_file(self):
        for path in (RUNBOOK, ADAPTER):
            found = slugs(path)
            self.assertEqual(len(found), len(set(found)), f'duplicate nn: slug in {path.name}')

    def test_every_runbook_rule_reaches_the_adapter(self):
        missing = set(slugs(RUNBOOK)) - set(slugs(ADAPTER))
        self.assertFalse(missing, f'{sorted(missing)} are in the runbook but not the adapter — '
                                  'the agent is guaranteed to read the adapter, so a rule '
                                  'only in the runbook is not a constraint')

    def test_the_adapter_invents_no_rule_of_its_own(self):
        extra = set(slugs(ADAPTER)) - set(slugs(RUNBOOK))
        self.assertFalse(extra, f'{sorted(extra)} are in the adapter but not the runbook, '
                                'which is the source of truth for behaviour')


if __name__ == '__main__':
    unittest.main()
