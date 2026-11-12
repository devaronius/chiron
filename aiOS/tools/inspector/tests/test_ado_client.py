"""The inspector's Azure DevOps adapter, against a fake transport and a fake git.

Nothing here touches the network or a repository: every request goes to `FakeAdo`, which
answers from fixtures and records what was sent, so the guards are asserted on what would
actually have reached Azure DevOps.
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
from client.ado import Ado, criteria_items, html_text  # noqa: E402

ME = 'dev@example.com'
CONFIG = {'ado': {'org': 'acme', 'project': 'Cargo App', 'repoName': 'mobile'},
          'agents': {'inspector': {'tracker': 'ado', 'releaseTargets': ['staging'],
                                   'releaseSources': ['development']}}}
RULES_TOML = '[naming]\nlevel = "medium"\n[string-punctuation]\nlevel = "low"\nceiling = "low"\n'
RULES = {'naming': {'level': 'medium'}, 'string-punctuation': {'level': 'low', 'ceiling': 'low'}}
REPO = '/Cargo%20App/_apis/git/repositories/mobile'
SIGNED = core.signature(ME)

PR7 = {'pullRequestId': 7, 'title': 'feat(5): x', 'description': 'Does x.', 'status': 'active',
       'createdBy': {'uniqueName': ME}, 'sourceRefName': 'refs/heads/feat/5-x',
       'targetRefName': 'refs/heads/development',
       'lastMergeSourceCommit': {'commitId': 'src1'}, 'lastMergeTargetCommit': {'commitId': 'tgt1'},
       'lastMergeCommit': {'commitId': 'mrg1'}, 'repository': {'project': {'id': 'proj-id'}}}


class FakeAdo:
    """The REST API, answered from fixtures keyed by (method, path suffix)."""

    def __init__(self, answers=None):
        self.answers = {('GET', '/_apis/connectionData'): {'authenticatedUser': {
                            'properties': {'Account': {'$value': ME}}}},
                        ('GET', f'{REPO}/pullRequests/7'): PR7,
                        ('GET', f'{REPO}/pullRequests/7/workitems'): {'value': [{'id': '5'}]},
                        ('GET', f'{REPO}/pullRequests/7/threads'): {'value': []},
                        **(answers or {})}
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, method, url, body=None):
        self.calls.append((method, url, body))
        path = url.split('?', 1)[0]
        if method == 'PATCH' and path.split('/')[-2] == 'threads':
            return {'id': int(path.rsplit('/', 1)[1])}  # a real thread answers with itself
        for (m, suffix), answer in self.answers.items():
            if m == method and path.endswith(suffix):
                return answer
        return {}

    def writes(self):
        return [(m, u.split('?', 1)[0], b) for m, u, b in self.calls if m != 'GET']


class FakeGit:
    def __init__(self, diff='', names='lib/a.dart\n', root='/repo'):
        self.out = {'diff': diff, 'names': names, 'root': root}
        self.calls = []

    def __call__(self, *args, auth=None):
        self.calls.append((args, auth))
        if args[0] == 'merge-base':
            return 'base1\n'
        if args[0] == 'rev-parse':
            return self.out['root'] + '\n'
        if args[0] == 'diff':
            return self.out['names'] if '--name-only' in args else self.out['diff']
        return ''


def ado(fake=None, git=None):
    return Ado(CONFIG, request=fake or FakeAdo(), run_git=git or FakeGit(), auth=lambda: 'Basic x')


def finding(slug='bad name', severity='medium', rule='naming', path='lib/a.dart', line=3):
    return {'slug': slug, 'severity': severity, 'rule': rule, 'summary': f'{slug} summary',
            'fix': 'Rename it.', 'path': path, 'line': line}


def report(*findings):
    sends_back = any(core.SEVERITIES.index(f['severity']) <= 2 for f in findings)
    return {'pr': 7, 'ticket': '5', 'basis': '#5 AC1', 'tests': 'ran a, green',
            'recommendation': 'Waiting for author' if sends_back else 'Approve',
            'findings': list(findings), 'commit': 'abc1234'}


def thread(id, content, author=ME, status='active', path='/lib/a.dart', replies=()):
    return {'id': id, 'status': status,
            'threadContext': {'filePath': path} if path else None,
            'comments': [{'id': 1, 'content': content, 'author': {'uniqueName': author}},
                         *({'id': i + 2, 'content': r, 'author': {'uniqueName': 'x'}}
                           for i, r in enumerate(replies))]}


def rendered(f):
    key = core.finding_key('5', f['path'], f['slug'])
    return core.render_finding(f, key, ME)


# ---------------------------------------------------------------- config and reads


class GivenTheConfig(unittest.TestCase):
    def test_WHEN_the_ado_section_is_incomplete_THEN_it_names_each_missing_key(self):
        with self.assertRaisesRegex(core.InspectorError, '`ado.project`, `ado.repoName`'):
            Ado({'ado': {'org': 'acme'}})

    def test_WHEN_the_tracker_is_ado_THEN_the_ado_adapter_is_built(self):
        self.assertIsInstance(cli.adapter_from_config(CONFIG), Ado)

    def test_WHEN_a_repoId_is_set_THEN_the_API_uses_it_and_the_web_link_the_name(self):
        client = Ado({'ado': {**CONFIG['ado'], 'repoId': 'r-1'}}, request=FakeAdo())
        self.assertTrue(client.repo_api.endswith('/git/repositories/r-1'))


class GivenAPullRequest(unittest.TestCase):
    def test_THEN_it_is_normalised_with_only_its_linked_work_items(self):
        pr = ado().pull_request(7)
        self.assertEqual((pr['base'], pr['head'], pr['head_sha'], pr['tickets']),
                         ('development', 'feat/5-x', 'src1', [5]))
        self.assertEqual(pr['url'], 'https://dev.azure.com/acme/Cargo%20App/_git/mobile/pullrequest/7')

    def test_WHEN_the_diff_is_asked_for_THEN_it_is_three_dot_from_namespaced_refs(self):
        git = FakeGit(diff='the diff')
        self.assertEqual(ado(git=git).diff(7), 'the diff')
        fetch = git.calls[0]
        self.assertEqual(fetch[1], 'Basic x')  # through the environment, never argv
        self.assertIn('+refs/heads/feat/5-x:refs/inspector/feat/5-x', fetch[0])
        self.assertEqual(git.calls[-1][0], ('diff', 'base1', 'refs/inspector/feat/5-x'))

    def test_THEN_any_line_of_a_changed_file_anchors_and_other_files_do_not(self):
        can = ado().anchors(7)
        self.assertTrue(can('lib/a.dart', 999))
        self.assertFalse(can('lib/b.dart', 1))


class GivenAWorkItem(unittest.TestCase):
    def item(self, **fields):
        fake = FakeAdo({('GET', '/_apis/wit/workitems/5'): {'fields': {
            'System.Title': 'T', 'System.State': 'Active', 'System.Tags': 'a; b', **fields}}})
        return ado(fake).ticket(5)

    def test_WHEN_the_criteria_are_a_list_THEN_each_top_level_item_is_one_AC(self):
        item = self.item(**{'Microsoft.VSTS.Common.AcceptanceCriteria':
                            '<ol><li>one<ul><li>detail</li></ul></li><li>two &amp; more</li></ol>'})
        self.assertEqual(item['criteria'], ['one detail', 'two & more'])
        self.assertEqual(item['labels'], ['a', 'b'])

    def test_WHEN_they_are_gherkin_scenarios_THEN_each_scenario_is_one_AC(self):
        raw = ('<b>Scenario: first</b><ul><li>Given a, </li><li>When b, </li><li>Then c.</li></ul>\n'
               '<b>Scenario: second</b><ul><li>Given d</li></ul>')
        self.assertEqual(criteria_items(raw), ['Scenario: first Given a, When b, Then c.',
                                               'Scenario: second Given d'])

    def test_WHEN_the_criteria_are_prose_THEN_each_line_is_one_AC(self):
        self.assertEqual(criteria_items('<div>first</div><div>second</div>'), ['first', 'second'])

    def test_WHEN_there_are_no_criteria_THEN_None(self):
        self.assertIsNone(self.item()['criteria'])

    def test_WHEN_it_is_a_bug_THEN_its_repro_steps_are_in_the_body(self):
        item = self.item(**{'Microsoft.VSTS.TCM.ReproSteps': '<p>tap save</p>'})
        self.assertIn('## Repro steps\n\ntap save', item['body'])

    def test_THEN_links_and_images_keep_their_targets(self):
        self.assertEqual(html_text('<p><a href="https://f.ig/x">design</a> <img src="s.png"></p>'),
                         'design (https://f.ig/x) [image] (s.png)')

    def test_WHEN_story_runs_THEN_the_criteria_are_numbered_from_the_field(self):
        fake = FakeAdo({('GET', '/_apis/wit/workitems/5'): {'fields': {
            'System.Title': 'T', 'Microsoft.VSTS.Common.AcceptanceCriteria': '<ul><li>a</li></ul>'}}})
        self.assertEqual(cli.story(ado(fake), 5)['acceptance_criteria'], {'#5 AC1': 'a'})


class GivenTheRequiredBuild(unittest.TestCase):
    def build(self, context, status='approved', blocking=True):
        fake = FakeAdo({('GET', '/_apis/policy/evaluations'): {'value': [
            {'status': status, 'configuration': {'isBlocking': blocking},
             'context': {'buildId': 42, **context}}]}})
        client = ado(fake)
        return client.build(client.pull_request(7)), fake

    CURRENT = {'lastMergeSourceCommitId': 'src1', 'lastMergeTargetCommitId': 'tgt1',
               'lastMergeCommitId': 'mrg1'}

    def test_WHEN_it_validated_this_merge_THEN_approved_and_current(self):
        out, fake = self.build(self.CURRENT)
        self.assertEqual((out['state'], out['current'], out['build_id']), ('approved', True, 42))
        self.assertIn('artifactId=vstfs%3A%2F%2F%2FCodeReview%2FCodeReviewId%2Fproj-id%2F7',
                      fake.calls[-1][1])

    def test_WHEN_it_validated_an_older_head_THEN_not_current(self):
        out, _ = self.build({**self.CURRENT, 'lastMergeSourceCommitId': 'old'})
        self.assertEqual((out['state'], out['current']), ('approved', False))

    def test_WHEN_it_was_rejected_THEN_failed(self):
        self.assertEqual(self.build(self.CURRENT, status='rejected')[0]['state'], 'failed')

    def test_WHEN_no_blocking_policy_carries_a_build_THEN_none(self):
        self.assertEqual(self.build(self.CURRENT, blocking=False)[0]['state'], 'none')


class GivenTheTemplate(unittest.TestCase):
    def test_THEN_it_is_found_where_azure_devops_looks(self):
        with tempfile.TemporaryDirectory() as root:
            (pathlib.Path(root) / '.azuredevops').mkdir()
            (pathlib.Path(root) / '.azuredevops' / 'Pull_Request_Template.md').write_text('## A\n')
            self.assertEqual(ado(git=FakeGit(root=root)).template(), '## A\n')

    def test_WHEN_there_is_none_THEN_None(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(ado(git=FakeGit(root=root)).template())


# ---------------------------------------------------------------- posts


class GivenThreadsOnThePr(unittest.TestCase):
    def test_WHEN_another_account_planted_our_key_THEN_it_is_not_ours(self):
        key = 'qa:5:lib/a.dart:bad-name'
        fake = FakeAdo({('GET', f'{REPO}/pullRequests/7/threads'): {'value': [
            thread(1, f'x <!-- {key} -->'),
            thread(2, f'y <!-- {key} -->', author='colleague@example.com'),
            thread(3, 'a human question'),
            {'id': 4, 'status': 'active', 'comments': [{'id': 1, 'commentType': 'system'}]},
            thread(5, '<!-- qa:summary:7 -->', status='closed', path=None),
        ]}})
        mine = ado(fake).mine(7)
        self.assertEqual([(p.thread, p.anchored, p.resolved) for p in mine],
                         [('1', True, False), ('5', False, True)])


class GivenAPlanToApply(unittest.TestCase):
    def apply(self, rep, threads=()):
        fake = FakeAdo({('GET', f'{REPO}/pullRequests/7/threads'): {'value': list(threads)}})
        client = ado(fake)
        pr = client.pull_request(7)
        plan = core.plan_sync(rep, 7, ME, client.mine(7), client.anchors(7), RULES)
        return client.apply(pr, plan), fake.writes()

    def test_WHEN_a_finding_is_new_THEN_a_thread_anchors_with_a_leading_slash(self):
        done, writes = self.apply(report(finding()))
        method, url, body = writes[0]
        self.assertEqual((method, url.endswith('/pullRequests/7/threads')), ('POST', True))
        self.assertEqual(body['threadContext']['filePath'], '/lib/a.dart')
        self.assertEqual(body['status'], 'active')
        self.assertIn('summary posted', done)

    def test_WHEN_the_rule_has_a_ceiling_THEN_the_thread_lands_closed(self):
        _, writes = self.apply(report(finding(severity='low', rule='string-punctuation')))
        self.assertEqual(writes[0][2]['status'], 'closed')

    def test_WHEN_a_finding_is_gone_THEN_one_reply_and_the_thread_is_fixed(self):
        _, writes = self.apply(report(), [thread(9, rendered(finding()))])
        self.assertEqual(writes[0][1].rsplit('/', 2)[-2:], ['9', 'comments'])
        self.assertIn('No longer reproduces as of `abc1234`', writes[0][2]['content'])
        self.assertEqual((writes[1][0], writes[1][2]), ('PATCH', {'status': 'fixed'}))

    def test_WHEN_a_finding_we_fixed_comes_back_THEN_it_is_reactivated_with_a_reply(self):
        gone = f'No longer reproduces as of `old`.\n\n{SIGNED}'
        _, writes = self.apply(report(finding()),
                               [thread(9, rendered(finding()), status='fixed', replies=[gone])])
        self.assertEqual(writes[0][2], {'status': 'active'})
        self.assertIn('Reproduces again', writes[1][2]['content'])

    def test_WHEN_the_finding_changed_THEN_the_lead_comment_is_edited_in_place(self):
        _, writes = self.apply(report({**finding(), 'summary': 'sharper'}),
                               [thread(9, rendered(finding()))])
        self.assertEqual((writes[0][0], writes[0][1].rsplit('/', 3)[-3:]),
                         ('PATCH', ['9', 'comments', '1']))

    def test_WHEN_the_summary_is_unchanged_THEN_nothing_is_written(self):
        body = core.render_summary(report(), core.summary_key(7), ME, [])
        _, writes = self.apply(report(), [thread(5, body, path=None)])
        self.assertEqual(writes, [])

    def test_WHEN_a_status_patch_changes_nothing_THEN_it_is_an_error_not_a_claim(self):
        class Silent(FakeAdo):  # Azure DevOps on a thread id that does not exist
            def __call__(self, method, url, body=None):
                return {}

        fake = Silent()
        post = core.Posted('qa:5:x:y', '1', 'b', True, False, '9', ['b'])
        with self.assertRaisesRegex(core.InspectorError, 'thread does not exist'):
            ado(fake)._status(7, post, 'fixed')

    def test_THEN_nothing_sent_could_be_a_vote_or_a_work_item_write(self):
        _, writes = self.apply(report(finding()), [thread(8, rendered(finding(slug='gone')))])
        for _, url, _ in writes:
            self.assertNotIn('/reviewers', url)
            self.assertNotIn('/wit/', url)


# ---------------------------------------------------------------- the CLI


def run_cli(argv, client):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv, client, CONFIG)
    return code, out.getvalue(), err.getvalue()


class GivenTheCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / 'rules.toml').write_text(RULES_TOML)
        patch = mock.patch.object(cli.grading, 'RULES_PATH', self.dir / 'rules.toml')
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, rep):
        path = self.dir / 'findings-7.json'
        path.write_text(json.dumps(rep))
        return str(path)

    def test_WHEN_the_PR_merges_a_release_source_THEN_sync_refuses(self):
        fake = FakeAdo({('GET', f'{REPO}/pullRequests/7'):
                        {**PR7, 'sourceRefName': 'refs/heads/development',
                         'targetRefName': 'refs/heads/main'}})
        code, _, err = run_cli(['sync', '--pr', '7', '--report', self.write(report())], ado(fake))
        self.assertEqual(code, 1)
        self.assertIn('release integration (merges development)', err)
        self.assertEqual(fake.writes(), [])

    def test_WHEN_the_report_passes_THEN_findings_and_summary_are_posted(self):
        fake = FakeAdo()
        code, out, err = run_cli(['sync', '--pr', '7', '--report', self.write(report(finding()))],
                                 ado(fake))
        self.assertEqual(code, 0, err)
        self.assertIn('posted qa:5:lib/a.dart:bad-name', out)
        self.assertEqual(len(fake.writes()), 2)

    def test_WHEN_no_work_item_is_linked_THEN_body_says_so_in_ado_terms(self):
        with tempfile.TemporaryDirectory() as root:
            (pathlib.Path(root) / 'pull_request_template.md').write_text('## What\n')
            fake = FakeAdo({('GET', f'{REPO}/pullRequests/7/workitems'): {'value': []},
                            ('GET', f'{REPO}/pullRequests/7'): {**PR7, 'description': '## What\nx'}})
            code, out, _ = run_cli(['body', '--pr', '7'], ado(fake, FakeGit(root=root)))
        self.assertEqual(code, 0)
        problems = json.loads(out)
        self.assertEqual([p['rule'] for p in problems], ['missing-work-item'])
        self.assertIn('Work items', problems[0]['fix'])


if __name__ == '__main__':
    unittest.main()
