"""The inspector's PR client — core planner, GitHub adapter and CLI, against a fake `gh`.

Nothing here touches the network:
every `gh` call goes to `FakeGh`, which answers from fixtures and records what was sent,
so the guards are asserted on what would actually have reached GitHub.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import pr as cli  # noqa: E402
from client import core  # noqa: E402
from client.github import REVIEW_EVENT, GitHub, build_state, commentable_lines  # noqa: E402

LOGIN = 'devaronius'
RULES = {'naming': {'level': 'medium'}, 'pr-body': {'level': 'low'},
         'string-punctuation': {'level': 'low', 'ceiling': 'low'}}
RULES_TOML = """
[naming]
level = "medium"
[pr-body]
level = "low"
[string-punctuation]
level = "low"
ceiling = "low"
"""
CONFIG = {'agents': {'inspector': {'tracker': 'github', 'bodyCheck': 'body',
                                   'releaseTargets': ['production'],
                                   'testAffecting': ['.dart', 'pubspec.yaml', 'goldens/']}}}
PATTERNS = CONFIG['agents']['inspector']['testAffecting']


def anchor(lines: dict):
    """`can_anchor` over {path: {line, ...}}."""
    return lambda path, line: line in lines.get(path, ())


def gh_pr(number=7, head_sha='headsha'):
    """The normalised PR `apply` is handed."""
    return {'number': number, 'head_sha': head_sha}


class FakeGh:
    """`gh`, answered from fixtures. Records every call as (args, stdin)."""

    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, args, stdin=None):
        self.calls.append((list(args), stdin))
        for prefix, answer in self.answers.items():
            if ' '.join(args).startswith(prefix):
                return answer(args, stdin) if callable(answer) else answer
        return ''

    def writes(self):
        return [(a, s) for a, s in self.calls if '--method' in a
                or (a[:2] == ['api', 'graphql'] and 'resolveReviewThread' in ' '.join(a))]


def finding(slug='bad name', severity='medium', rule='naming', path='lib/a.dart', line=3,
            **extra):
    return {'slug': slug, 'severity': severity, 'rule': rule, 'summary': f'{slug} summary',
            'fix': 'Rename it.', 'path': path, 'line': line, **extra}


def report(*findings, **extra):
    sends_back = any(core.SEVERITIES.index(f['severity']) <= 2 for f in findings)
    return {'pr': 7, 'ticket': '5', 'basis': '#5 AC1', 'tests': 'ran a, green',
            'recommendation': 'Waiting for author' if sends_back else 'Approve',
            'findings': list(findings), 'commit': 'abc1234', **extra}


GONE_REPLY = f'No longer reproduces as of `old1234`.\n\n{core.signature(LOGIN)}'
NOTED_REPLY = f'Now a note as of `old1234` — nothing to change.\n\n{core.signature(LOGIN)}'


HUMAN = 'Still broken on my device — reopening.'
BACK_REPLY = f'Reproduces again as of `old1234`.\n\n{core.signature(LOGIN)}'


def posted(f, *, anchored=True, resolved=False, id='11', body=None, replies=()):
    """One of our posts; `replies` is the rest of its thread, oldest first."""
    key = core.finding_key('5', f.get('path', ''), f['slug'])
    body = body or core.render_finding(f, key, LOGIN)
    return core.Posted(key, id, body, anchored, resolved, 'T1' if anchored else None,
                       [body, *replies])


# ---------------------------------------------------------------- core


class GivenAFindingKey(unittest.TestCase):
    def test_WHEN_the_line_moves_THEN_the_key_does_not(self):
        self.assertEqual(core.finding_key('5', 'lib/a.dart', 'Bad  Name!'),
                         'qa:5:lib/a.dart:bad-name')

    def test_WHEN_a_body_carries_it_THEN_it_is_read_back(self):
        body = core.render_finding(finding(), 'qa:5:lib/a.dart:bad-name', LOGIN)
        self.assertEqual(core.key_of(body), 'qa:5:lib/a.dart:bad-name')
        self.assertIn(f'run by {LOGIN}', body)


class GivenATicketBody(unittest.TestCase):
    def test_WHEN_it_has_an_Acceptance_criteria_section_THEN_each_bullet_is_one_AC(self):
        body = ('Intro\n\n## Acceptance criteria\n- [ ] one\n- [x] two\n* three\n\n'
                '## Related\n- not an AC\n')
        self.assertEqual(core.acceptance_criteria(body), ['one', 'two', 'three'])

    def test_WHEN_the_heading_is_plain_Acceptance_at_level_3_THEN_it_counts(self):
        self.assertEqual(core.acceptance_criteria('### Acceptance\n- only\n## Next\n- no'),
                         ['only'])

    def test_WHEN_a_deeper_heading_sits_inside_THEN_the_section_continues(self):
        body = '## Acceptance\n- a\n### Detail\n- b\n## Out\n- c'
        self.assertEqual(core.acceptance_criteria(body), ['a', 'b'])

    def test_WHEN_an_AC_has_nested_bullets_THEN_they_join_it_rather_than_count(self):
        body = '## Acceptance criteria\n- [ ] `sync`:\n  - new ones\n  - old ones\n- [ ] next'
        self.assertEqual(core.acceptance_criteria(body), ['`sync`: new ones old ones', 'next'])

    def test_WHEN_the_ACs_are_numbered_THEN_each_one_counts(self):
        body = '## Acceptance criteria\n1. one\n2) two\n10. ten\n## Next'
        self.assertEqual(core.acceptance_criteria(body), ['one', 'two', 'ten'])

    def test_WHEN_an_AC_wraps_onto_the_next_line_THEN_it_stays_one_AC(self):
        body = ('## Acceptance\n- the first criterion runs\nonto a second line\n'
                '- [ ] second, wrapped\n  with an indent\n\nA paragraph after.\n- third')
        self.assertEqual(core.acceptance_criteria(body),
                         ['the first criterion runs onto a second line',
                          'second, wrapped with an indent', 'third'])

    def test_WHEN_it_has_no_such_section_THEN_None_not_an_empty_list(self):
        self.assertIsNone(core.acceptance_criteria('## Context\n- prose'))


TEMPLATE = '''<!-- intro -->
## Type
<!-- check one -->
- [ ] `feat`
- [ ] `fix`

## What and why

Closes #

## Departures from the ticket
<!-- write None. -->
'''


class GivenAPrBodyAgainstTheTemplate(unittest.TestCase):
    def problems(self, body):
        return {(p['rule'], p['severity'], p['summary']) for p in
                core.body_problems(TEMPLATE, body)}

    def test_WHEN_every_section_is_filled_THEN_nothing_is_reported(self):
        body = '## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n\n## Departures from the ticket\nNone.\n'
        self.assertEqual(core.body_problems(TEMPLATE, body), [])

    def test_WHEN_a_section_is_missing_THEN_low_with_the_templates_casing(self):
        body = '## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n'
        self.assertIn(('pr-body', 'low',
                       'the `## Departures from the ticket` section of the PR template is missing'),
                      self.problems(body))

    def test_WHEN_CI_checks_the_headings_THEN_a_missing_one_is_left_to_CI(self):
        body = '## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n'
        self.assertEqual(core.body_problems(TEMPLATE, body, ci_checks_headings=True), [])

    def test_WHEN_CI_checks_the_headings_THEN_an_empty_one_is_still_medium(self):
        body = ('## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n\n'
                '## Departures from the ticket\n-\n')
        self.assertEqual([(p['severity'], p['summary']) for p in
                          core.body_problems(TEMPLATE, body, ci_checks_headings=True)],
                         [('medium', '`## Departures from the ticket` is empty')])

    def test_WHEN_a_section_holds_only_a_comment_or_a_bare_dash_THEN_medium(self):
        body = ('## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n\n'
                '## Departures from the ticket\n<!-- todo -->\n-\n')
        self.assertIn(('pr-body', 'medium', '`## Departures from the ticket` is empty'),
                      self.problems(body))

    def test_WHEN_two_types_are_ticked_THEN_it_is_reported(self):
        body = ('## Type\n- [x] `feat`\n- [x] `fix`\n\n## What and why\nCloses #5\n\n'
                '## Departures from the ticket\nNone.\n')
        self.assertIn(('pr-body', 'low', '`## Type` has 2 boxes ticked, not one'),
                      self.problems(body))


class GivenASyncPlan(unittest.TestCase):
    commentable = {'lib/a.dart': {3, 4}}

    def plan(self, rep, mine=()):
        return core.plan_sync(rep, 7, LOGIN, list(mine), anchor(self.commentable), RULES)

    def test_WHEN_a_finding_is_new_and_on_a_diff_line_THEN_it_is_posted_anchored(self):
        plan = self.plan(report(finding()))
        self.assertEqual([(n['path'], n['line']) for n in plan.new], [('lib/a.dart', 3)])
        self.assertFalse(plan.new[0]['resolve'])

    def test_WHEN_its_line_is_outside_the_diff_THEN_it_goes_in_the_summary(self):
        plan = self.plan(report(finding(path='lib/b.dart', line=9)))
        self.assertEqual(plan.new, [])
        self.assertIn('Findings outside the diff', plan.summary[1])
        self.assertIn('`lib/b.dart:9`', plan.summary[1])

    def test_WHEN_a_note_is_reported_THEN_it_is_never_its_own_post(self):
        plan = self.plan(report(finding(severity='note', rule='naming', line=3)))
        self.assertEqual(plan.new, [])

    def test_WHEN_an_existing_post_says_the_same_THEN_nothing_is_rewritten(self):
        f = finding()
        self.assertEqual(self.plan(report(f), [posted(f)]).edits, [])

    def test_WHEN_the_finding_changed_THEN_its_post_is_rewritten_in_place(self):
        f = finding()
        plan = self.plan(report({**f, 'severity': 'high', 'failure': 'x → crash'}),
                         [posted(f)])
        self.assertEqual(len(plan.edits), 1)
        self.assertIn('**HIGH**', plan.edits[0][1])
        self.assertEqual(plan.new, [])

    def test_WHEN_a_posted_finding_is_gone_THEN_one_reply_names_the_commit(self):
        plan = self.plan(report(), [posted(finding())])
        self.assertEqual(len(plan.stale), 1)
        self.assertIn('`abc1234`', plan.stale[0][1])

    def test_WHEN_a_finding_we_marked_fixed_comes_back_THEN_its_thread_reopens(self):
        plan = self.plan(report(finding()), [posted(finding(), resolved=True, replies=[GONE_REPLY])])
        self.assertEqual(len(plan.reopen), 1)
        self.assertIn('Reproduces again as of `abc1234`', plan.reopen[0][1])

    # The client posts as a person, so a human resolving the thread by hand carries the
    # same login as the client — only the last comment tells the two apart.
    def test_WHEN_it_was_resolved_by_hand_on_the_same_account_THEN_it_stays_resolved(self):
        plan = self.plan(report(finding()), [posted(finding(), resolved=True)])
        self.assertEqual(plan.reopen, [])

    def test_WHEN_someone_else_wrote_the_last_reply_THEN_it_stays_resolved(self):
        reply = 'No longer reproduces as of `x`, agreed — closing.'
        plan = self.plan(report(finding()), [posted(finding(), resolved=True, replies=[reply])])
        self.assertEqual(plan.reopen, [])

    def test_WHEN_a_report_only_rule_stays_reported_THEN_its_thread_is_not_reopened(self):
        f = finding(severity='low', rule='string-punctuation')
        self.assertEqual(self.plan(report(f), [posted(f, resolved=True)]).reopen, [])

    def test_WHEN_a_posted_finding_is_regraded_to_note_THEN_it_is_rewritten_and_resolved(self):
        f = finding()
        plan = self.plan(report({**f, 'severity': 'note'}), [posted(f)])
        self.assertEqual(plan.stale, [])
        self.assertEqual(len(plan.edits), 1)
        self.assertIn('**NOTE**', plan.edits[0][1])
        self.assertEqual([p.key for p, _ in plan.settle], [plan.edits[0][0].key])
        self.assertTrue(plan.settle[0][1].startswith('Now a note as of `abc1234`'))

    # Reopening adds no comment, so a thread a human reopened still ends in our closing
    # reply — that is how the client knows to leave it alone.
    def test_WHEN_a_human_reopened_a_thread_we_marked_fixed_THEN_no_second_reply(self):
        plan = self.plan(report(), [posted(finding(), replies=[GONE_REPLY])])
        self.assertEqual(plan.stale, [])

    def test_WHEN_a_human_reopened_a_note_we_settled_THEN_it_is_not_closed_again(self):
        f = finding()
        plan = self.plan(report({**f, 'severity': 'note'}), [posted(f, replies=[NOTED_REPLY])])
        self.assertEqual(plan.settle, [])

    # A human who reopens with a comment pushes the client's reply off the end of the
    # thread; it still decides from its own last action, not from the last comment.
    def test_WHEN_a_human_reopened_with_a_comment_THEN_no_second_fixed_reply(self):
        plan = self.plan(report(), [posted(finding(), replies=[GONE_REPLY, HUMAN])])
        self.assertEqual(plan.stale, [])

    def test_WHEN_a_human_reopened_a_settled_note_with_a_comment_THEN_it_stays_open(self):
        f = finding()
        plan = self.plan(report({**f, 'severity': 'note'}),
                         [posted(f, replies=[NOTED_REPLY, HUMAN])])
        self.assertEqual(plan.settle, [])

    def test_WHEN_the_finding_returns_on_a_thread_a_human_reopened_THEN_it_says_so(self):
        plan = self.plan(report(finding()), [posted(finding(), replies=[GONE_REPLY, HUMAN])])
        self.assertEqual(len(plan.reopen), 1)

    def test_WHEN_we_already_said_it_is_back_and_a_human_resolved_it_THEN_left_alone(self):
        plan = self.plan(report(finding()),
                         [posted(finding(), resolved=True, replies=[GONE_REPLY, BACK_REPLY])])
        self.assertEqual(plan.reopen, [])

    def test_WHEN_a_settled_note_is_regraded_back_up_THEN_its_thread_reopens(self):
        plan = self.plan(report(finding()), [posted(finding(), resolved=True, replies=[NOTED_REPLY])])
        self.assertEqual(len(plan.reopen), 1)

    def test_WHEN_that_note_thread_is_already_resolved_THEN_it_is_not_resolved_again(self):
        f = finding()
        self.assertEqual(self.plan(report({**f, 'severity': 'note'}),
                                   [posted(f, resolved=True)]).settle, [])

    def test_WHEN_it_is_gone_but_already_resolved_THEN_it_is_left_alone(self):
        self.assertEqual(self.plan(report(), [posted(finding(), resolved=True)]).stale, [])

    def test_WHEN_the_rule_has_a_ceiling_THEN_the_post_is_resolved_as_it_lands(self):
        plan = self.plan(report(finding(severity='low', rule='string-punctuation')))
        self.assertTrue(plan.new[0]['resolve'])

    def test_WHEN_a_summary_exists_THEN_it_is_the_one_edited(self):
        summary = core.Posted(core.summary_key(7), '99', 'old', False)
        self.assertIs(self.plan(report(), [summary]).summary[0], summary)


class GivenCheckRuns(unittest.TestCase):
    def test_THEN_one_word_describes_them(self):
        ok = {'status': 'completed', 'conclusion': 'success'}
        self.assertEqual(build_state([]), 'none')
        self.assertEqual(build_state([ok, {'status': 'queued'}]), 'queued')
        self.assertEqual(build_state([ok, {'status': 'in_progress'}]), 'running')
        self.assertEqual(build_state([ok, {**ok, 'conclusion': 'skipped'}]), 'approved')
        self.assertEqual(build_state([ok, {**ok, 'conclusion': 'failure'}]), 'failed')


class GivenAWorkingTree(unittest.TestCase):
    def test_WHEN_an_untracked_package_holds_tests_THEN_its_dart_files_count(self):
        raw = '?? modules/x/test/a_test.dart\n M docs/n.md\nR  old.dart -> lib/new.dart\n'
        self.assertEqual(core.test_affecting(core.porcelain_paths(raw), PATTERNS),
                         ['lib/new.dart', 'modules/x/test/a_test.dart'])

    def test_WHEN_no_patterns_are_configured_THEN_every_dirty_path_counts(self):
        self.assertEqual(core.test_affecting(['docs/n.md', 'a.dart']), ['a.dart', 'docs/n.md'])

    def test_WHEN_a_golden_image_changed_THEN_it_counts(self):
        raw = ' M apps/cms/test/design/goldens/board.png\n M docs/shot.png\n'
        self.assertEqual(core.test_affecting(core.porcelain_paths(raw), PATTERNS),
                         ['apps/cms/test/design/goldens/board.png'])


# ---------------------------------------------------------------- the GitHub adapter


DIFF = '''diff --git a/lib/a.dart b/lib/a.dart
index 1..2 100644
--- a/lib/a.dart
+++ b/lib/a.dart
@@ -1,3 +1,4 @@
 keep
-gone
+one
+two
 tail
'''


def gh_with(pr_comments=(), issue_comments=(), threads=None):
    lines = lambda rows: '\n'.join(json.dumps(r) for r in rows)
    threads = threads or {}
    nodes = [{'id': t[0], 'isResolved': t[1], 'comments': {'nodes': [
                 {'databaseId': c, 'body': 'first'}, *({'databaseId': 0, 'body': b} for b in t[2:])]}}
             for c, t in threads.items()]
    return FakeGh({
        'api user': LOGIN + '\n',
        'repo view': json.dumps({'owner': {'login': 'devaronius'}, 'name': 'gcms'}),
        'api repos/{owner}/{repo}/pulls/7/comments': lines(pr_comments),
        'api repos/{owner}/{repo}/issues/7/comments': lines(issue_comments),
        'api graphql -f query=\nquery': json.dumps({'data': {'repository': {'pullRequest': {
            'reviewThreads': {'pageInfo': {'hasNextPage': False, 'endCursor': None},
                              'nodes': nodes}}}}}),
    })


class GivenADiff(unittest.TestCase):
    def test_THEN_added_and_context_lines_are_commentable_and_removed_ones_are_not(self):
        self.assertEqual(commentable_lines(DIFF), {'lib/a.dart': {1, 2, 3, 4}})


class GivenPostsOnThePr(unittest.TestCase):
    def test_WHEN_another_account_planted_our_key_THEN_it_is_not_ours(self):
        key = 'qa:5:lib/a.dart:bad-name'
        fake = gh_with(pr_comments=[{'id': 1, 'body': f'x <!-- {key} -->', 'user': LOGIN},
                                    {'id': 2, 'body': f'y <!-- {key} -->', 'user': 'colleague'},
                                    {'id': 3, 'body': 'a human question', 'user': LOGIN}],
                       issue_comments=[{'id': 4, 'body': '<!-- qa:summary:7 -->', 'user': 'colleague'}],
                       threads={1: ('T1', False), 2: ('T2', False), 3: ('T3', False)})
        self.assertEqual([p.id for p in GitHub(run=fake).mine(7)], ['1'])


    def test_WHEN_a_thread_has_replies_THEN_all_of_them_are_read(self):
        key = 'qa:5:lib/a.dart:bad-name'
        fake = gh_with(pr_comments=[{'id': 1, 'body': f'<!-- {key} -->', 'user': LOGIN}],
                       threads={1: ('T1', True, GONE_REPLY, HUMAN)})
        post = GitHub(run=fake).mine(7)[0]
        self.assertEqual((post.resolved, post.comments), (True, ['first', GONE_REPLY, HUMAN]))


class GivenAPlanToApply(unittest.TestCase):
    def test_WHEN_findings_are_new_THEN_one_review_goes_out_with_event_COMMENT(self):
        fake = gh_with()
        plan = core.plan_sync(report(finding(), finding(slug='other', line=4)), 7, LOGIN, [],
                              anchor(commentable_lines(DIFF)), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        reviews = [json.loads(s) for a, s in fake.calls if a[-3:-1] == ['repos/{owner}/{repo}/pulls/7/reviews', '--input']]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]['event'], 'COMMENT')
        self.assertEqual(reviews[0]['commit_id'], 'headsha')
        self.assertEqual(len(reviews[0]['comments']), 2)

    def test_THEN_nothing_sent_could_be_a_vote(self):
        self.assertEqual(REVIEW_EVENT, 'COMMENT')
        fake = gh_with()
        f = finding()
        plan = core.plan_sync(report(f), 7, LOGIN, [posted(finding(slug='gone'))],
                              anchor(commentable_lines(DIFF)), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        sent = ' '.join(' '.join(a) + (s or '') for a, s in fake.calls)
        self.assertNotIn('APPROVE', sent)
        self.assertNotIn('REQUEST_CHANGES', sent)

    def test_WHEN_a_finding_is_gone_THEN_its_thread_gets_a_reply_and_is_resolved(self):
        fake = gh_with()
        plan = core.plan_sync(report(), 7, LOGIN, [posted(finding())], anchor({}), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        writes = [' '.join(a) for a, _ in fake.writes()]
        self.assertTrue(any('pulls/7/comments/11/replies' in w for w in writes))
        self.assertTrue(any('resolveReviewThread' in w and 'id=T1' in w for w in writes))

    def test_WHEN_a_report_only_finding_lands_THEN_its_new_thread_is_resolved(self):
        f = finding(severity='low', rule='string-punctuation')
        key = core.finding_key('5', f['path'], f['slug'])
        # What GitHub returns once the review is in: our comment, in an open thread.
        fake = gh_with(pr_comments=[{'id': 21, 'body': f'x <!-- {key} -->', 'user': LOGIN}],
                       threads={21: ('T9', False)})
        plan = core.plan_sync(report(f), 7, LOGIN, [], anchor(commentable_lines(DIFF)), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        self.assertTrue(any('resolveReviewThread' in ' '.join(a) and 'id=T9' in a
                            for a, _ in fake.writes()))

    def test_WHEN_a_thread_we_resolved_regresses_THEN_it_is_unresolved_with_a_reply(self):
        f = finding()
        fake = gh_with()
        plan = core.plan_sync(report(f), 7, LOGIN, [posted(f, resolved=True, replies=[GONE_REPLY])],
                              anchor(commentable_lines(DIFF)), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        writes = [' '.join(a) for a, _ in fake.writes()]
        self.assertTrue(any('unresolveReviewThread' in w and 'id=T1' in w for w in writes))
        self.assertTrue(any('pulls/7/comments/11/replies' in w and 'Reproduces again' in w
                            for w in writes))

    def test_WHEN_a_finding_becomes_a_note_THEN_its_thread_gets_a_note_reply_and_resolves(self):
        f = finding()
        fake = gh_with()
        plan = core.plan_sync(report({**f, 'severity': 'note'}), 7, LOGIN, [posted(f)], anchor({}),
                              RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        writes = [' '.join(a) for a, _ in fake.writes()]
        self.assertTrue(any('query=mutation' in w and 'resolveReviewThread' in w
                            and 'unresolve' not in w and 'id=T1' in w for w in writes))
        self.assertTrue(any('pulls/7/comments/11/replies' in w and 'Now a note as of' in w
                            for w in writes))

    def test_WHEN_the_thread_is_already_open_THEN_it_is_told_without_an_unresolve(self):
        f = finding()
        fake = gh_with()
        plan = core.plan_sync(report(f), 7, LOGIN, [posted(f, replies=[GONE_REPLY, HUMAN])],
                              anchor(commentable_lines(DIFF)), RULES)
        GitHub(run=fake).apply(gh_pr(), plan)
        writes = [' '.join(a) for a, _ in fake.writes()]
        self.assertFalse(any('unresolveReviewThread' in w for w in writes))
        self.assertTrue(any('/replies' in w and 'Reproduces again' in w for w in writes))

    def test_WHEN_the_summary_is_unchanged_THEN_it_is_not_edited(self):
        rep = report()
        body = core.render_summary(rep, core.summary_key(7), LOGIN, [])
        summary = core.Posted(core.summary_key(7), '99', body, False)
        fake = gh_with()
        GitHub(run=fake).apply(gh_pr(head_sha='h'), core.plan_sync(rep, 7, LOGIN, [summary], anchor({}), RULES))
        self.assertEqual(fake.writes(), [])

    def test_WHEN_the_summary_changed_THEN_it_is_patched_as_a_conversation_comment(self):
        summary = core.Posted(core.summary_key(7), '99', 'stale', False)
        fake = gh_with()
        GitHub(run=fake).apply(gh_pr(head_sha='h'), core.plan_sync(report(), 7, LOGIN, [summary], anchor({}), RULES))
        self.assertEqual([a[3] for a, _ in fake.writes()],
                         ['repos/{owner}/{repo}/issues/comments/99'])


# ---------------------------------------------------------------- the CLI


def run_cli(argv, client):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv, client, CONFIG)
    return code, out.getvalue(), err.getvalue()


PR7 = {'number': 7, 'title': 'feat(9): x', 'body': 'Closes #5', 'state': 'OPEN', 'url': 'u',
       'author': {'login': LOGIN}, 'baseRefName': 'main', 'headRefName': 'feat/5-x',
       'headRefOid': 'headsha', 'closingIssuesReferences': [{'number': 5}]}
TICKET5 = {'number': 5, 'title': 't', 'body': '## Acceptance\n- one\n- two', 'state': 'OPEN',
           'url': 'u5', 'labels': []}


def cli_gh(pr=PR7):
    fake = gh_with()
    fake.answers.update({'pr view 7': json.dumps(pr), 'issue view 5': json.dumps(TICKET5),
                         'issue view 9': json.dumps({**TICKET5, 'number': 9}),
                         'pr diff 7': DIFF})
    return fake


class GivenTheConfig(unittest.TestCase):
    def test_WHEN_the_tracker_has_no_adapter_THEN_it_says_so(self):
        with self.assertRaisesRegex(core.InspectorError, "no adapter for 'gitlab'"):
            cli.adapter_from_config({'agents': {'inspector': {'tracker': 'gitlab'}}})

    def test_WHEN_no_tracker_is_set_THEN_it_names_the_key(self):
        with self.assertRaisesRegex(core.InspectorError, 'agents.inspector.tracker'):
            cli.adapter_from_config({})

    def test_WHEN_the_tracker_is_github_THEN_the_GitHub_adapter_is_built(self):
        self.assertIsInstance(cli.adapter_from_config(CONFIG), GitHub)


class GivenShowAndStory(unittest.TestCase):
    def test_WHEN_the_title_names_another_number_THEN_only_the_closing_ticket_is_read(self):
        code, out, _ = run_cli(['show', '--pr', '7'], GitHub(run=cli_gh()))
        self.assertEqual(code, 0)
        shown = json.loads(out)
        self.assertEqual([t['number'] for t in shown['tickets']], [5])
        self.assertEqual(shown['tickets'][0]['acceptance_criteria'],
                         {'#5 AC1': 'one', '#5 AC2': 'two'})

    def test_WHEN_a_ticket_has_no_Acceptance_section_THEN_a_reason_not_an_error(self):
        fake = cli_gh()
        fake.answers['issue view 5'] = json.dumps({**TICKET5, 'body': 'prose only'})
        code, out, _ = run_cli(['story', '--ticket', '5'], GitHub(run=fake))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['acceptance_criteria'], {})
        self.assertIn('no acceptance criteria', json.loads(out)['reason'])


class GivenBody(unittest.TestCase):
    MISSING = 'the `## Departures from the ticket` section of the PR template is missing'

    def body(self, runs):
        fake = cli_gh({**PR7, 'body': '## Type\n- [x] `feat`\n\n## What and why\nCloses #5\n'})
        fake.answers.update({
            'api repos/{owner}/{repo}/contents/.github/PULL_REQUEST_TEMPLATE.md': TEMPLATE,
            'api repos/{owner}/{repo}/commits/headsha/check-runs':
                '\n'.join(json.dumps(r) for r in runs)})
        code, out, err = run_cli(['body', '--pr', '7'], GitHub(CONFIG, run=fake))
        self.assertEqual(code, 0, err)
        return [p['summary'] for p in json.loads(out)]

    def test_WHEN_the_body_check_ran_on_the_head_THEN_a_missing_heading_is_left_to_it(self):
        runs = [{'name': 'body', 'status': 'completed', 'conclusion': 'failure'}]
        self.assertNotIn(self.MISSING, self.body(runs))

    def test_WHEN_only_other_checks_ran_THEN_a_missing_heading_is_reported(self):
        runs = [{'name': 'dart', 'status': 'completed', 'conclusion': 'success'}]
        self.assertIn(self.MISSING, self.body(runs))

    def test_WHEN_Closes_carries_no_number_and_nothing_is_linked_THEN_missing_work_item(self):
        body = ('## Type\n- [x] `feat`\n\n## What and why\nCloses #\n<!-- Closes #9 -->\n\n'
                '## Departures from the ticket\nNone.\n')
        fake = cli_gh({**PR7, 'body': body, 'closingIssuesReferences': []})
        fake.answers['api repos/{owner}/{repo}/contents/.github/PULL_REQUEST_TEMPLATE.md'] = TEMPLATE
        code, out, err = run_cli(['body', '--pr', '7'], GitHub(run=fake))
        self.assertEqual(code, 0, err)
        self.assertEqual([p['rule'] for p in json.loads(out)], ['missing-work-item'])


class GivenSync(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rules = pathlib.Path(tmp.name) / 'severity-rules.toml'
        rules.write_text(RULES_TOML)
        patch = mock.patch.object(cli.grading, 'RULES_PATH', rules)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, rep):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(rep, tmp)
        tmp.close()
        self.addCleanup(pathlib.Path(tmp.name).unlink)
        return tmp.name

    def test_WHEN_the_report_was_written_for_another_PR_THEN_nothing_is_posted(self):
        fake = cli_gh()
        code, _, err = run_cli(['sync', '--pr', '7', '--report',
                                self.write({**report(finding()), 'pr': 8})], GitHub(run=fake))
        self.assertEqual(code, 1)
        self.assertIn('written for PR 8', err)
        self.assertEqual(fake.writes(), [])

    def test_WHEN_the_grader_refuses_THEN_nothing_is_posted(self):
        fake = cli_gh()
        code, _, err = run_cli(['sync', '--pr', '7', '--report',
                                self.write(report(finding(severity='low')))], GitHub(run=fake))
        self.assertEqual(code, 1)
        self.assertIn('below the floor', err)
        self.assertEqual(fake.writes(), [])

    def test_WHEN_the_PR_is_release_integration_THEN_it_is_refused(self):
        fake = cli_gh({**PR7, 'baseRefName': 'production'})
        code, _, err = run_cli(['sync', '--pr', '7', '--report', self.write(report())],
                               GitHub(run=fake))
        self.assertEqual(code, 1)
        self.assertIn('release integration', err)
        self.assertEqual(fake.writes(), [])

    def test_WHEN_the_report_passes_THEN_findings_and_summary_are_posted(self):
        fake = cli_gh()
        code, out, err = run_cli(['sync', '--pr', '7', '--report', self.write(report(finding()))],
                                 GitHub(run=fake))
        self.assertEqual(code, 0, err)
        self.assertIn('posted qa:5:lib/a.dart:bad-name', out)
        self.assertIn('summary posted', out)


if __name__ == '__main__':
    unittest.main()
