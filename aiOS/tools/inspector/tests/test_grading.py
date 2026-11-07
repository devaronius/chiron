"""grading.py — the ladder, the rule floors, and what a report must carry before anyone
reads it as a review.

The rules come from a fixture file rather than the installed one: the installed list is
the human's and changes, while what is under test here is the mechanism. The installed
list's own shape is checked separately, and only where chiron has installed it.
"""
from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'grading.py'
_spec = importlib.util.spec_from_file_location('grading', _PATH)
grading = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grading)

RULES = '''
[ac-unmet]
level = "critical"
covers = "an AC does not hold"
why = "the change fails its own purpose"

[missing-test]
level = "high"
covers = "behaviour with no test"
why = "never shown to work"

[naming]
level = "medium"
covers = "a misleading name"
why = "names outlive code"

[string-punctuation]
level = "low"
covers = "punctuation"
why = "cosmetic"

[pr-body]
level = "low"
ceiling = "low"
covers = "a broken PR body"
why = "report-only"
'''

CRITICAL = {
    'severity': 'critical', 'rule': 'ac-unmet', 'slug': 'emits after close',
    'summary': 'the state holder emits after close',
    'failure': 'Leave the page mid-fetch → StateError on the completed future.',
    'evidence': '`run the trips test` → StateError: cannot emit after close',
    'fix': 'Guard the emit.', 'path': 'lib/trips.x', 'line': 42,
}
NAMING = {'severity': 'medium', 'rule': 'naming', 'slug': 'misleading name',
          'summary': '`count` holds a total', 'fix': 'Rename it `total`.'}
PUNCTUATION = {'severity': 'low', 'rule': 'string-punctuation', 'slug': 'full stop',
               'summary': 'one string lacks its full stop', 'fix': 'Add it.'}
BODY = {'severity': 'low', 'rule': 'pr-body', 'slug': 'bare box',
        'summary': 'an unticked box gives no reason', 'fix': 'Give it a reason.'}
CAPPED = 'Reviewed in part — nothing at medium or above in what I read'
COVERAGE = 'reviewed 18 of 63 files (cap: 40). Not reviewed: assets/**'


def report(**over) -> dict:
    base = {'pr': 812, 'recommendation': 'Waiting for author', 'basis': '#44244 AC1–AC4',
            'tests': 'ran the touched package, green', 'findings': [dict(CRITICAL)]}
    base.update(over)
    return base


class GradingCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        rules = pathlib.Path(self._dir.name) / 'severity-rules.toml'
        rules.write_text(RULES)
        patch = mock.patch.object(grading, 'RULES_PATH', rules)
        patch.start()
        self.addCleanup(patch.stop)

    def passes(self, rep: dict, pr=None) -> dict:
        return grading.check_report(rep, pr)

    def refused(self, rep: dict, pr=None) -> str:
        with self.assertRaises(grading.InspectorError) as caught:
            grading.check_report(rep, pr)
        return str(caught.exception)


class TestTheLadder(GradingCase):
    def test_a_critical_finding_with_failure_and_evidence_passes(self):
        self.assertEqual(self.passes(report())['findings'][0]['severity'], 'critical')

    def test_critical_without_evidence_is_refused(self):
        finding = dict(CRITICAL)
        del finding['evidence']
        self.assertIn('critical finding without `evidence`',
                      self.refused(report(findings=[finding])))

    def test_critical_without_a_failure_is_refused(self):
        finding = dict(CRITICAL)
        del finding['failure']
        self.assertIn('critical finding without a `failure`',
                      self.refused(report(findings=[finding])))

    def test_high_without_a_failure_is_refused(self):
        finding = {'severity': 'high', 'rule': 'missing-test', 'slug': 'untested',
                   'summary': 'the retry path has no test', 'fix': 'Add one.'}
        self.assertIn('high finding without a `failure`',
                      self.refused(report(findings=[finding])))

    def test_a_posted_finding_without_a_fix_is_refused(self):
        finding = dict(NAMING)
        del finding['fix']
        self.assertIn('medium finding without a `fix`',
                      self.refused(report(findings=[finding])))

    def test_a_note_needs_no_fix(self):
        note = {'severity': 'note', 'rule': 'unlisted', 'slug': 'aside',
                'summary': 'worth knowing'}
        self.passes(report(findings=[note], recommendation='Approve'))

    def test_an_unknown_severity_is_refused(self):
        self.assertIn("unknown severity 'blocking'",
                      self.refused(report(findings=[dict(NAMING, severity='blocking')])))


class TestTheRuleFloors(GradingCase):
    def test_a_finding_without_a_rule_is_refused(self):
        finding = dict(NAMING)
        del finding['rule']
        self.assertIn('missing `rule`', self.refused(report(findings=[finding])))

    def test_a_rule_that_is_not_listed_is_refused(self):
        self.assertIn("unknown rule 'bad-vibes'",
                      self.refused(report(findings=[dict(NAMING, rule='bad-vibes')])))

    def test_unlisted_is_graded_by_the_ladder_alone(self):
        finding = dict(PUNCTUATION, rule='unlisted')
        self.passes(report(findings=[finding], recommendation='Approve'))

    def test_a_finding_graded_under_its_floor_is_refused(self):
        message = self.refused(report(findings=[dict(NAMING, severity='low')],
                                      recommendation='Approve'))
        self.assertIn("below the floor of rule 'naming' (medium)", message)

    def test_a_finding_may_be_graded_above_its_floor(self):
        finding = dict(NAMING, severity='high', failure='`count` is summed twice.')
        self.passes(report(findings=[finding]))

    def test_a_finding_above_its_rules_ceiling_is_refused(self):
        message = self.refused(report(findings=[dict(BODY, severity='medium')]))
        self.assertIn("above the ceiling of rule 'pr-body' (low)", message)

    def test_a_finding_at_its_ceiling_still_allows_approval(self):
        self.passes(report(findings=[BODY], recommendation='Approve'))

    def test_a_missing_rule_list_is_refused_rather_than_graded_without_floors(self):
        with mock.patch.object(grading, 'RULES_PATH', pathlib.Path(self._dir.name) / 'gone'):
            self.assertIn('no rule list', self.refused(report()))


class TestTheVerdict(GradingCase):
    """The recommendation is derived from the grades, in both directions."""

    def test_medium_cannot_be_recommended_for_approval(self):
        self.assertIn('Waiting for author',
                      self.refused(report(findings=[NAMING], recommendation='Approve')))

    def test_low_findings_and_notes_alone_allow_approval(self):
        self.passes(report(findings=[PUNCTUATION], recommendation='Approve'))

    def test_nothing_at_medium_or_above_cannot_be_sent_back(self):
        self.assertIn('nothing at medium or above',
                      self.refused(report(findings=[PUNCTUATION])))

    def test_reject_is_never_the_inspectors(self):
        self.assertIn("unknown recommendation 'Reject'",
                      self.refused(report(findings=[], recommendation='Reject')))

    def test_a_capped_review_may_recommend_in_part(self):
        self.passes(report(findings=[PUNCTUATION], recommendation=CAPPED, coverage=COVERAGE))

    def test_a_capped_review_cannot_recommend_approval(self):
        self.assertIn('a capped review',
                      self.refused(report(findings=[PUNCTUATION], recommendation='Approve',
                                          coverage=COVERAGE)))

    def test_a_full_review_cannot_claim_to_be_in_part(self):
        self.assertIn('no `coverage`',
                      self.refused(report(findings=[PUNCTUATION], recommendation=CAPPED)))

    def test_a_capped_review_with_a_medium_finding_still_sends_it_back(self):
        self.passes(report(findings=[NAMING], coverage=COVERAGE))


class TestThePullRequestItNames(GradingCase):
    def test_a_report_for_another_pr_is_refused(self):
        self.assertIn('written for PR 812, not PR 813', self.refused(report(), pr=813))

    def test_a_report_with_no_pr_cannot_be_posted(self):
        rep = report()
        del rep['pr']
        self.assertIn('missing `pr`', self.refused(rep, pr=812))

    def test_a_session_review_needs_no_pr(self):
        rep = report()
        del rep['pr']
        self.passes(rep)

    def test_a_follow_up_without_a_target_is_refused(self):
        rep = report(follow_ups=[{'slug': 'rate limit', 'summary': 'a 429 next story'}])
        self.assertIn('follow-up without a `target`', self.refused(rep))


class TestTheCommandLine(GradingCase):
    def run_cli(self, rep: dict, *extra: str) -> tuple[int, str, str]:
        path = pathlib.Path(self._dir.name) / 'findings-812.json'
        path.write_text(json.dumps(rep))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = grading.main([str(path), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_a_passing_report_exits_zero_and_counts_the_grades(self):
        code, out, _ = self.run_cli(report(), '--pr', '812')
        self.assertEqual(code, 0)
        self.assertIn('1 critical', out)

    def test_a_refused_report_exits_one_with_the_reason(self):
        code, _, err = self.run_cli(report(recommendation='Approve'))
        self.assertEqual(code, 1)
        self.assertIn('Waiting for author', err)


class TestTheInstalledRuleList(unittest.TestCase):
    """The installed list is the human's override; a malformed one silently changes every
    verdict, so its shape is checked rather than trusted."""

    def setUp(self):
        if not grading.RULES_PATH.is_file():
            self.skipTest('no installed severity-rules.toml — chiron seeds it on install')

    def test_every_rule_names_a_level_and_says_what_it_covers_and_why(self):
        for name, rule in grading.load_rules().items():
            with self.subTest(rule=name):
                self.assertIn(rule.get('level'), grading.SEVERITIES)
                if 'ceiling' in rule:
                    self.assertIn(rule['ceiling'], grading.SEVERITIES)
                self.assertTrue((rule.get('covers') or '').strip())
                self.assertTrue((rule.get('why') or '').strip())

    def test_unlisted_is_reserved_rather_than_defined(self):
        self.assertNotIn('unlisted', grading.load_rules())


if __name__ == '__main__':
    unittest.main()
