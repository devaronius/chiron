"""vault-report's schedule capability check.

`aiOS/` is the vendor-neutral ring, and a schedule is the one thing in it allowed to
name a concrete harness — the daily briefing drives a browser at the Firebase console,
the day note reads Teams through an MCP connector. Undeclared, that dependency is
invisible until a run under a harness lacking it produces an empty section, and a stale
Crashlytics table reads as a fresh one.

Schedules are written into a temp directory and `SCHEDULES_DIR` is pointed at it, so
nothing here depends on what the real `aiOS/schedules/` happens to contain.
"""
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'vault-report.py'
_spec = importlib.util.spec_from_file_location('vault_report', _PATH)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)

WITHOUT = '## Without browser-control\n\nFall back to the last dated snapshot.\n'


class ScheduleCapabilityCase(unittest.TestCase):
    """Writes one schedule per test and runs the check against it alone."""

    def check(self, frontmatter: str, body: str = '') -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / 'probe.md').write_text(f'---\nname: probe\n{frontmatter}---\n\nPrompt.\n\n{body}')
            # REPO_ROOT moves with it: the check reports paths relative to the repo,
            # so a temp dir outside it would raise rather than report.
            prior = vr.SCHEDULES_DIR, vr.V.REPO_ROOT
            vr.SCHEDULES_DIR, vr.V.REPO_ROOT = d, d
            try:
                return vr.check_schedule_capabilities()
            finally:
                vr.SCHEDULES_DIR, vr.V.REPO_ROOT = prior

    def only(self, *args, **kwargs) -> str:
        issues = self.check(*args, **kwargs)
        self.assertEqual(len(issues), 1, f'expected exactly one issue, got {issues}')
        return issues[0]


class TestDeclaration(ScheduleCapabilityCase):
    def test_a_portable_schedule_declares_an_empty_list_and_passes(self):
        self.assertEqual(self.check('requires: []\n'), [])

    def test_omitting_requires_is_reported_rather_than_assumed_portable(self):
        # The whole point: silence must not read as "any harness can run this".
        self.assertIn('no `requires:`', self.only(''))

    def test_an_unknown_capability_is_named_in_the_message(self):
        self.assertIn('telepathy', self.only('requires: ["telepathy"]\n', WITHOUT))


class TestKnownCapabilities(ScheduleCapabilityCase):
    def test_browser_control_with_its_section_passes(self):
        self.assertEqual(self.check('requires: ["browser-control"]\n', WITHOUT), [])

    def test_any_mcp_server_is_accepted_as_a_family(self):
        body = '## Without mcp:microsoft-365\n\nDefer to step 6.\n'
        self.assertEqual(self.check('requires: ["mcp:microsoft-365"]\n', body), [])

    def test_each_declared_capability_needs_its_own_section(self):
        body = '## Without browser-control\n\nFall back.\n'
        issue = self.only('requires: ["browser-control", "mcp:teams"]\n', body)
        self.assertIn('mcp:teams', issue)


class TestWithoutSectionIsAHeading(ScheduleCapabilityCase):
    """Regression: the first cut matched a substring and so passed on a mention.

    daily-briefing step 5 says "if the fetch fails, see `## Without browser-control`".
    A substring check accepted that backticked reference as the section itself, and
    reported green with the section absent — the exact failure the check exists to
    catch, hidden by the prose that points at it.
    """

    def test_a_declared_capability_with_no_section_at_all_is_reported(self):
        self.assertIn('## Without browser-control',
                      self.only('requires: ["browser-control"]\n'))

    def test_a_backticked_mention_does_not_count_as_the_section(self):
        body = 'If the fetch fails, see `## Without browser-control`.\n'
        self.assertIn('has no', self.only('requires: ["browser-control"]\n', body))

    def test_a_wrong_heading_level_does_not_count(self):
        body = '### Without browser-control\n\nFall back.\n'
        self.assertIn('has no', self.only('requires: ["browser-control"]\n', body))

    def test_a_heading_with_trailing_whitespace_still_counts(self):
        self.assertEqual(self.check('requires: ["browser-control"]\n',
                                    '## Without browser-control   \n\nFall back.\n'), [])


if __name__ == '__main__':
    unittest.main()
