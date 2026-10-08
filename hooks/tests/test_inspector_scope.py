"""The Inspector's scope, enforced in the harness rather than in prose.

The Inspector reviews other people's work and posts to their pull requests, so two
claims about it have to be mechanically true rather than well-intentioned: it cannot
change what it reviews, and it cannot reach the board except through `inspector.py`
— the script that deliberately has no verb for casting a vote. This hook is what
makes "the human keeps the sign-off" a boundary instead of a promise.

Tests are phrased as *refused* / *allowed* rather than as return values, because that
is the only thing the harness acts on.
"""
from __future__ import annotations

import json
import pathlib
import re
import unittest
from unittest import mock

from _harness import REPO_ROOT, inspector_scope as scope, settings


class ScopeCase(unittest.TestCase):
    def assertRefused(self, command: str):
        reason = scope.refuse_bash(command)
        self.assertIsNotNone(reason, f'expected refusal: {command!r}')
        return reason

    def assertAllowed(self, command: str):
        self.assertIsNone(scope.refuse_bash(command), f'expected allowed: {command!r}')


class TestReviewingWithoutChanging(ScopeCase):
    """The whole point: a reviewer that can edit launders its findings into changes."""

    def test_reading_history_and_diffs_is_allowed(self):
        for command in ('git diff origin/development...origin/feat/1-x',
                        'git fetch origin development',
                        'git merge-base origin/development origin/feat/1-x',
                        'git log --oneline -20',
                        'git show abc1234',
                        'git ls-files modules/trips'):
            self.assertAllowed(command)

    def test_every_way_of_changing_the_repo_is_refused(self):
        for command in ('git commit -am wip', 'git push origin HEAD', 'git reset --hard',
                        'git rebase development', 'git merge development',
                        'git cherry-pick abc1234', 'git stash', 'git apply patch.diff',
                        'git revert abc1234', 'git tag v1'):
            self.assertRefused(command)

    def test_checkout_is_refused_because_it_moves_the_branch_a_human_is_standing_on(self):
        reason = self.assertRefused('git checkout feat/45428-carrier')
        self.assertIn('worktree', reason)
        self.assertRefused('git switch development')


class TestWorktrees(ScopeCase):
    """A PR branch is reviewed in a worktree, which is the only sanctioned way to
    have someone else's code on disk without disturbing the human's checkout."""

    def test_a_worktree_under_the_scratchpad_is_allowed(self):
        self.assertAllowed('git worktree add /tmp/claude/scratchpad/pr812 origin/feat/1-x')
        self.assertAllowed('git worktree list')
        self.assertAllowed('git worktree remove /tmp/claude/scratchpad/pr812')

    def test_a_worktree_inside_the_repo_is_refused_because_it_is_still_the_repo(self):
        reason = self.assertRefused('git worktree add ./review origin/feat/1-x')
        self.assertIn('scratchpad', reason)

    def test_worktree_subcommands_beyond_the_list_are_refused(self):
        self.assertRefused('git worktree move a b')


CLIENT_PATH = '.claude/skills/pr-client/pr.py'


class TestBoardAccess(ScopeCase):
    """The project's pull-request client is the only route to the tracker, because it is
    the only route with no verb for voting.

    chiron ships no such client — a PR lives on a tracker the framework knows nothing
    about — so the project names one in `agents.inspector.scripts` and the hook compiles
    its matcher from that. With none configured, mode 2 is simply unavailable.
    """

    CLIENT = '.claude/skills/pr-client/pr.py'

    def setUp(self):
        patch = mock.patch.object(
            scope, 'SCRIPT_RE',
            re.compile(r'^python3?\s+\S*' + re.escape(CLIENT_PATH) + r'\b'))
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_inspector_script_is_allowed(self):
        self.assertAllowed('python3 .claude/skills/pr-client/pr.py show --pr 812')
        self.assertAllowed(
            'python3 .claude/skills/pr-client/pr.py sync --pr 812 --report f.json')

    def test_an_arbitrary_interpreter_would_reopen_every_endpoint_the_verbs_close(self):
        self.assertRefused('python3 -c "import urllib.request"')
        self.assertRefused('python3 -m http.server')
        self.assertRefused('python3 .claude/skills/other/other.py claim --ticket 1')

    def test_the_read_only_vault_reporters_are_allowed(self):
        """A docs PR's only real evidence is what these reporters measure.

        Without them the Inspector can restate the author's numbers but not
        reproduce them, which is not verification.
        """
        for command in (
            'python3 aiOS/tools/ideaVerse/vault-lint.py',
            'python3 aiOS/tools/ideaVerse/vault-lint.py -q --categories',
            'python3 aiOS/tools/wiki/wiki-sync.py',
            'python3 aiOS/tools/wiki/wiki-sync.py --quiet',
            'python3 aiOS/tools/ideaVerse/research-capture.py check docs/note.md',
            'python3 aiOS/tools/ideaVerse/research-capture.py exists carrier',
        ):
            self.assertAllowed(command)

    def test_a_reporter_reached_through_a_scratchpad_worktree_is_still_allowed(self):
        self.assertAllowed(
            'python3 /tmp/scratchpad/wt/aiOS/tools/ideaVerse/vault-lint.py')

    def test_the_flags_that_make_a_reporter_write_are_refused(self):
        """Read-only has to be a boundary, not a convention the agent observes."""
        for command in (
            'python3 aiOS/tools/ideaVerse/vault-lint.py --fix',
            'python3 aiOS/tools/ideaVerse/vault-lint.py -f',
            'python3 aiOS/tools/wiki/wiki-sync.py --update',
            'python3 aiOS/tools/wiki/wiki-sync.py -u',
        ):
            self.assertRefused(command)

    def test_only_the_flags_a_reporter_may_receive_are_allowed(self):
        """The list is what a script MAY be given; everything else `-…` is refused.

        Blocklisting the write flags was tried first and was not a boundary: argparse
        accepts `--u` for `--update`, and the shell hands the hook `--upd\\atex` or
        `$(echo --update)` while argparse receives the real spelling. An allowlist
        survives all three, because an obfuscated flag is still unrecognised.
        """
        for command in (
            'python3 aiOS/tools/wiki/wiki-sync.py --u',
            'python3 aiOS/tools/wiki/wiki-sync.py --upd',
            'python3 aiOS/tools/wiki/wiki-sync.py --updat',
            'python3 aiOS/tools/wiki/wiki-sync.py --update=1',
            'python3 aiOS/tools/ideaVerse/vault-lint.py --f',
            'python3 aiOS/tools/ideaVerse/vault-lint.py --fi',
            # the shapes the QA demonstrated defeating a spelling blocklist
            'python3 aiOS/tools/wiki/wiki-sync.py --upd\\atex',
            'python3 aiOS/tools/wiki/wiki-sync.py $(echo --update)',
            'python3 aiOS/tools/wiki/wiki-sync.py --UPDATE',
            'python3 aiOS/tools/wiki/wiki-sync.py -- --update',
            'python3 aiOS/tools/wiki/wiki-sync.py --quiet --update',
            # an unknown flag is refused even when it writes nothing
            'python3 aiOS/tools/wiki/wiki-sync.py --colour',
        ):
            self.assertRefused(command)

    def test_a_positional_is_not_mistaken_for_a_flag(self):
        self.assertAllowed('python3 aiOS/tools/ideaVerse/research-capture.py check docs/a-b.md')
        self.assertAllowed('python3 aiOS/tools/ideaVerse/research-capture.py exists carrier')

    def test_an_unrelated_long_flag_is_not_swept_up_by_the_prefix_rule(self):
        for command in ('python3 aiOS/tools/wiki/wiki-sync.py --quiet',
                        'python3 aiOS/tools/ideaVerse/vault-lint.py --categories',
                        'python3 aiOS/tools/ideaVerse/vault-lint.py --quiet'):
            self.assertAllowed(command)

    def test_note_review_is_allowed_and_has_no_write_flag_at_all(self):
        self.assertAllowed('python3 aiOS/tools/ideaVerse/note-review.py docs/x.md')
        self.assertAllowed('python3 aiOS/tools/ideaVerse/note-review.py docs/x.md --json')

    def test_a_write_flag_bundled_into_a_short_cluster_is_still_refused(self):
        self.assertRefused('python3 aiOS/tools/wiki/wiki-sync.py -qu')
        self.assertRefused('python3 aiOS/tools/ideaVerse/vault-lint.py -qf')

    def test_wiki_sync_update_names_the_reason_it_matters(self):
        reason = self.assertRefused('python3 aiOS/tools/wiki/wiki-sync.py --update')
        self.assertIn('wiki-sync.py', reason)
        self.assertIn('--update', reason)

    def test_widening_to_the_reporters_did_not_open_the_interpreter(self):
        """The reason the rule exists: a named script, not a way in."""
        for command in (
            'python3 -c "import urllib.request"',
            'python3 aiOS/tools/ideaVerse/vault-lint.py; python3 -c "import os"',
            'python3 aiOS/tools/ideaVerse/kanban-sync.py',
            'python3 aiOS/tools/ideaVerse/vault-report.py',
        ):
            self.assertRefused(command)

    def test_curl_is_refused_outright_including_a_vote(self):
        reason = self.assertRefused(
            'curl -X PUT https://tracker.example.test/api/repositories/r/'
            'pullRequests/812/reviewers/me')
        self.assertIn('no verb that votes', reason)
        self.assertRefused('curl -sS https://tracker.example.test/api/projects')

    def test_heredocs_are_refused_because_they_smuggle_an_interpreter(self):
        self.assertRefused('cat x <<EOF\nrm -rf /\nEOF')


class TestToolchain(ScopeCase):
    """The Inspector runs the tests itself — that is what makes a red test a fact
    rather than an opinion."""

    def test_the_repo_test_runner_is_allowed_by_exact_path(self):
        """A reviewer who cannot run the suite can only repeat the author's count —
        which is how "543 tests" survived two passes while the real number was 545."""
        for command in ('./aiOS/tools/run-tests.sh', 'aiOS/tools/run-tests.sh',
                        './aiOS/tools/run-tests.sh -v',
                        './aiOS/tools/run-tests.sh --coverage',
                        '/Users/x/wt/aiOS/tools/run-tests.sh'):
            self.assertAllowed(command)

    def test_the_runner_may_redirect_stderr_because_a_failing_run_is_unreadable_without_it(self):
        self.assertAllowed('./aiOS/tools/run-tests.sh 2>&1 | tail -20')
        self.assertAllowed('./aiOS/tools/run-tests.sh 2>/dev/null')

    def test_allowing_the_runner_did_not_open_the_shell(self):
        for command in ('bash aiOS/tools/run-tests.sh', 'sh run-tests.sh', './deploy.sh',
                        './aiOS/tools/run-tests.sh --exec rm',
                        './aiOS/tools/run-tests.sh > /tmp/x',
                        './aiOS/tools/run-tests.sh; curl https://evil',
                        'python3 -m unittest discover -s .'):
            self.assertRefused(command)

    def test_a_configured_build_command_is_allowed(self):
        # `agents.inspector.buildCommands` — empty by default, because a framework
        # cannot know a project's toolchain and guessing one grants a shell head
        # nobody asked for.
        with mock.patch.object(scope, 'BUILD_HEADS', {'flutter', 'dart', 'go'}):
            for command in ('flutter test modules/trips', 'dart analyze',
                            'go test ./...'):
                self.assertAllowed(command)

    def test_an_unconfigured_build_command_is_refused(self):
        with mock.patch.object(scope, 'BUILD_HEADS', set()):
            self.assertRefused('flutter test modules/trips')

    def test_read_only_shell_is_allowed_including_a_quoted_pipe(self):
        self.assertAllowed("grep -rn 'foo' modules | jq '.[] | .key'")
        self.assertAllowed('find . -name "*.dart" | wc -l')

    def test_an_unknown_head_is_refused_by_default(self):
        reason = self.assertRefused('gh pr view 812')
        self.assertIn('allowlist', reason)
        self.assertRefused('az repos pr list')
        self.assertRefused('rm -rf modules')


class TestWriteScope(unittest.TestCase):
    """Scratchpad only. Unlike researcher-scope.py this needs no repo root, because
    nothing inside any checkout is writable — which is also why the worktree
    path-resolution bug that bites the Researcher cannot bite here."""

    def assertRefused(self, path: str):
        self.assertIsNotNone(scope.refuse_write(path), f'expected refusal: {path!r}')

    def test_the_scratchpad_is_the_one_writable_place(self):
        self.assertIsNone(scope.refuse_write('/tmp/claude-502/x/scratchpad/findings.json'))

    def test_code_is_never_writable_because_a_reviewer_does_not_fix(self):
        self.assertRefused('modules/trips/lib/foo.dart')
        self.assertRefused('/Users/x/dev/project/apps/shop/lib/main.dart')

    def test_the_vault_and_the_harness_are_not_the_inspectors_either(self):
        self.assertRefused('docs/ideaVerse/efforts/works/x.md')
        self.assertRefused('.claude/agents/inspector.md')

    def test_a_worktree_of_the_repo_is_still_refused(self):
        self.assertRefused('/tmp/claude/scratchpad-worktrees/pr812/modules/trips/x.dart')

    def test_scratchpad_matches_a_path_segment_not_a_substring(self):
        # A checkout living under a directory whose name merely contains the word
        # must not switch the whole scope off.
        self.assertRefused('/Users/x/my-scratchpadding/modules/foo.dart')


class TestEdges(unittest.TestCase):
    def test_an_empty_path_is_refused_rather_than_waved_through(self):
        self.assertIsNotNone(scope.refuse_write(''))

    def test_a_bare_git_invocation_is_not_a_subcommand(self):
        self.assertIsNone(scope.refuse_bash('git --version'))


class TestWiring(unittest.TestCase):
    """The hook only runs if settings.json points at it, on the right event, for
    every tool it polices. Registered alongside researcher-scope.py on the same
    matcher — each self-gates on `agent_type`, so both can watch every call."""

    def setUp(self):
        self.settings = settings()
        if self.settings is None:
            self.skipTest('no .claude/settings.json — the hooks are not wired in this repo')
        if 'inspector-scope.py' not in json.dumps(self.settings.get('hooks', {})):
            self.skipTest('inspector-scope.py is not wired in this repo')

    def test_registered_on_pretooluse_and_not_on_stop(self):
        hooks = self.settings.get('hooks', {})
        self.assertIn('inspector-scope.py', json.dumps(hooks.get('PreToolUse', [])))
        self.assertNotIn('inspector-scope.py', json.dumps(hooks.get('Stop', [])))

    def test_the_matcher_covers_every_tool_the_hook_polices(self):
        matchers = [entry.get('matcher', '') for entry in self.settings['hooks']['PreToolUse']
                    if 'inspector-scope.py' in json.dumps(entry)]
        self.assertTrue(matchers, 'inspector-scope.py is not registered')
        for tool in ('Bash', 'Write', 'Edit', 'NotebookEdit'):
            self.assertTrue(any(tool in m for m in matchers), f'{tool} is not matched')

    def test_it_does_not_displace_the_researcher_hook(self):
        self.assertIn('researcher-scope.py', json.dumps(self.settings['hooks']['PreToolUse']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
