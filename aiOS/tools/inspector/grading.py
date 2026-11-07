#!/usr/bin/env python3
"""
grading — check an inspector report before anyone reads it as a review.

A report is the agent's judgement; this is what keeps it honest. Every check refuses
rather than corrects, so a malformed or overreaching report never reaches a pull request
under a human's name. It knows no tracker: the inspector runs it on its own findings file
in either mode, and a project's pull-request client calls `load_report()` before `sync`
posts anything.

The ladder is critical · high · medium · low · note. Each level says what it can prove:
critical names a failure and the evidence that reproduced it, high names a failure it did
not run, medium and low name a fix, a note names nothing. The floors per rule come from
`aiOS/runbooks/inspector/severity-rules.toml`, which is the human's and never written here.

Usage:
  python3 aiOS/tools/inspector/grading.py <findings.json>
  python3 aiOS/tools/inspector/grading.py <findings.json> --pr 812
  python3 aiOS/tools/inspector/grading.py - < findings.json

Exit codes: 0 — the report passes; 1 — refused, with the reason on stderr.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tomllib

# The ladder, highest first. Medium and up send a PR back.
SEVERITIES = ('critical', 'high', 'medium', 'low', 'note')
POSTED = ('critical', 'high', 'medium', 'low')  # notes fold into the summary

# Everything a review may recommend. The capped form is the runbook's Step 3.
RECOMMENDATIONS = (
    'Approve',
    'Waiting for author',
    'Reviewed in part — nothing at medium or above in what I read',
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
# The human's floors per rule. The inspector reads it and never writes it.
RULES_PATH = REPO_ROOT / 'aiOS' / 'runbooks' / 'inspector' / 'severity-rules.toml'


class InspectorError(RuntimeError):
    pass


def load_rules(path: pathlib.Path | None = None) -> dict[str, dict]:
    """Every rule in the floor list, by name."""
    path = path or RULES_PATH
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise InspectorError(
            f'no rule list at {path}. It is seeded by the chiron install; restore it '
            'rather than grading without floors.') from None


def rank(severity: str) -> int:
    """Position on the ladder; 0 is the most severe."""
    return SEVERITIES.index(severity)


def load_report(path: str, expected_pr: int | None = None) -> dict:
    """Read a findings file and refuse it unless every check passes."""
    raw = sys.stdin.read() if path == '-' else pathlib.Path(path).read_text(encoding='utf-8')
    return check_report(json.loads(raw), expected_pr)


def check_report(report: dict, expected_pr: int | None = None) -> dict:
    for field in ('recommendation', 'basis', 'tests', 'findings'):
        if field not in report:
            raise InspectorError(f'report is missing `{field}`')
    # The report names the PR it was written for, and it must be the one being posted
    # to. Without this, piping one review's findings at another PR succeeds silently —
    # a colleague receives someone else's review. Two agents defaulting to the same
    # scratchpad filename is all it takes, and that has happened.
    if expected_pr is not None:
        if 'pr' not in report:
            raise InspectorError('report is missing `pr`, so it cannot be posted to a PR')
        if str(report['pr']) != str(expected_pr):
            raise InspectorError(
                f'this report was written for PR {report["pr"]}, not PR {expected_pr}. '
                'Refusing to post one PR\'s findings to another. Check the report path.')
    rules = load_rules()
    for finding in report['findings']:
        check_finding(finding, rules)
    for follow_up in report.get('follow_ups', []):
        for field in ('slug', 'summary'):
            if field not in follow_up:
                raise InspectorError(f'follow-up is missing `{field}`: {follow_up}')
        if not follow_up.get('target'):
            raise InspectorError(
                f'follow-up without a `target`: {follow_up["slug"]}. Name the ticket it '
                'belongs to, or "new task: <proposed title>". The inspector proposes; it '
                'never creates the task.')
    check_verdict(report)
    return report


def check_finding(finding: dict, rules: dict[str, dict]) -> None:
    for field in ('severity', 'rule', 'summary', 'slug'):
        if field not in finding:
            raise InspectorError(f'finding is missing `{field}`: {finding}')
    severity, rule, slug = finding['severity'], finding['rule'], finding['slug']
    if severity not in SEVERITIES:
        raise InspectorError(f'unknown severity {severity!r}; one of {SEVERITIES}')
    if rule != 'unlisted' and rule not in rules:
        raise InspectorError(
            f'unknown rule {rule!r} on {slug}. Name a rule from {RULES_PATH.name}, or '
            '`unlisted` to propose one.')
    # A floor is the human's override. Grading under it would let the agent quietly
    # undo the decision the list exists to record.
    if rule in rules and rank(severity) > rank(rules[rule]['level']):
        raise InspectorError(
            f'{slug} is graded {severity}, below the floor of rule {rule!r} '
            f'({rules[rule]["level"]}). Raise it, or change the rule list.')
    # A ceiling marks a rule that reports before it may block: graded above it, a
    # finding would gate a merge the human has not yet decided it may gate.
    ceiling = (rules.get(rule) or {}).get('ceiling')
    if ceiling and rank(severity) < rank(ceiling):
        raise InspectorError(
            f'{slug} is graded {severity}, above the ceiling of rule {rule!r} '
            f'({ceiling}). It reports only; grade it {ceiling}.')
    # Each level says what it can prove. Critical means reproduced, so it names what was
    # run; high names a concrete failure that was not run.
    if severity in ('critical', 'high') and not finding.get('failure'):
        raise InspectorError(
            f'{severity} finding without a `failure`: {slug}. Name the concrete failure — '
            'these inputs, this wrong output — or grade it medium.')
    if severity == 'critical' and not finding.get('evidence'):
        raise InspectorError(
            f'critical finding without `evidence`: {slug}. Critical means reproduced — '
            'name the command or test that showed it and its output, or grade it high.')
    # A thread that only states a problem sends the author back to ask what to do about
    # it. Notes are exempt: they fold into the summary and are observations, not asks.
    if severity in POSTED and not finding.get('fix'):
        raise InspectorError(
            f'{severity} finding without a `fix`: {slug}. A posted finding names what to '
            'do about it. Write the remedy, or demote it to a note.')


def check_verdict(report: dict) -> None:
    """The recommendation follows from the grades, in both directions.

    Medium and up is a request for changes; below it is not. Left to the agent, the
    verdict drifts back to "nothing blocks, so Approve" with should-fixes open.
    """
    recommended = report['recommendation']
    if recommended not in RECOMMENDATIONS:
        raise InspectorError(
            f'unknown recommendation {recommended!r}; one of {RECOMMENDATIONS}. '
            '`Reject` is never the inspector\'s to make.')
    sends_back = any(rank(f['severity']) <= rank('medium') for f in report['findings'])
    capped = RECOMMENDATIONS[2]
    if recommended == capped and not report.get('coverage'):
        raise InspectorError(
            f'recommendation is {capped!r}, but the report carries no `coverage`. Name '
            'what was not read, or recommend on the full review.')
    if report.get('coverage') and not sends_back and recommended != capped:
        raise InspectorError(
            f'recommendation is {recommended!r} on a capped review (`coverage` is set). '
            f'You cannot approve what you did not read: recommend {capped!r}.')
    if sends_back and recommended != 'Waiting for author':
        raise InspectorError(
            f'recommendation is {recommended!r}, but a finding is graded medium or above, '
            'which makes it `Waiting for author`.')
    if not sends_back and recommended == 'Waiting for author':
        raise InspectorError(
            'recommendation is `Waiting for author` with nothing at medium or above. '
            'Raise the finding that justifies it, or recommend Approve.')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        allow_abbrev=False, description='Check an inspector findings file.')
    ap.add_argument('report', help='the findings file, or - for stdin')
    ap.add_argument('--pr', help='the PR this report will be posted to')
    args = ap.parse_args(argv)
    try:
        report = load_report(args.report, args.pr)
    except (InspectorError, OSError, json.JSONDecodeError) as e:
        print(f'✗ {e}', file=sys.stderr)
        return 1
    counts = {s: sum(f['severity'] == s for f in report['findings']) for s in SEVERITIES}
    graded = ', '.join(f'{n} {s}' for s, n in counts.items() if n) or 'no findings'
    print(f'✓ report passes — {graded}; recommendation: {report["recommendation"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
