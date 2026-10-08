"""The Researcher's write scope, enforced in the harness rather than in prose.

The Researcher runs unattended, so its constitution is documentation, not a boundary —
the first live run reached the remote through `publish` because it was told to, while
raw `git push` sat one Bash call away. This hook is what closes that, which makes it the
one script here whose failure mode is an agent doing something nobody sanctioned.

Tests are phrased as *refused* / *allowed* rather than as return values, because that is
the only thing the harness acts on.
"""
from __future__ import annotations

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

from _harness import REPO_ROOT, scope


class ScopeCase(unittest.TestCase):
    def assertRefused(self, command: str):
        reason = scope.refuse_bash(command)
        self.assertIsNotNone(reason, f'expected refusal: {command!r}')
        return reason

    def assertAllowed(self, command: str):
        self.assertIsNone(scope.refuse_bash(command), f'expected allowed: {command!r}')


class TestSegments(ScopeCase):
    def test_splits_on_every_separator_that_starts_a_new_program(self):
        self.assertEqual(scope.segments('ls; grep x && wc -l || true | sort'),
                         ['ls', 'grep x', 'wc -l', 'true', 'sort'])

    def test_a_pipe_inside_quotes_is_an_argument_not_a_pipeline(self):
        # This exact case refused a legitimate command on the hook's first live run.
        self.assertEqual(scope.segments("jq '.[] | .key' file.json"),
                         ["jq '.[] | .key' file.json"])

    def test_leading_environment_assignments_are_not_the_command(self):
        self.assertEqual(scope.segments('FOO=1 BAR=2 grep x'), ['grep x'])

    def test_command_substitution_is_neutralised_so_it_cannot_smuggle_a_head(self):
        self.assertNotIn('$(', ' '.join(scope.segments('echo $(git push)')))
        self.assertNotIn('`', ' '.join(scope.segments('echo `git push`')))

    def test_a_heredoc_body_is_not_parsed_as_code(self):
        self.assertEqual(scope.segments("cat <<'EOF'\ngit push\nEOF"), ['cat'])


class TestBashAllowlist(ScopeCase):
    def test_read_only_shell_tools_are_allowed(self):
        for command in ('grep -rn foo docs/', 'rg pattern', 'ls -la', 'wc -l file',
                        'jq .value file.json', 'shasum -a 256 file', 'sort | uniq -c'):
            with self.subTest(command=command):
                self.assertAllowed(command)

    def test_reaching_the_remote_directly_is_refused(self):
        for command in ('git push origin HEAD', 'git commit -m x', 'gh pr create',
                        'az repos pr create'):
            with self.subTest(command=command):
                self.assertIn('allowlist', self.assertRefused(command))

    def test_a_disallowed_head_later_in_a_pipeline_is_still_caught(self):
        self.assertRefused('grep -rn foo docs/ | git apply')

    def test_the_refusal_says_what_to_do_instead_of_working_around_it(self):
        reason = self.assertRefused('git push')
        self.assertIn('the scripts named above', reason)
        self.assertIn('report it instead of working around it', reason)


class TestInterpreters(ScopeCase):
    def test_the_two_scripts_that_own_board_and_vault_mechanics_are_allowed(self):
        self.assertAllowed('python3 aiOS/tools/ideaVerse/research-capture.py check n.md')
        self.assertAllowed('python3 aiOS/tools/ideaVerse/research-capture.py check note.md')

    def test_an_absolute_path_to_the_same_script_is_allowed(self):
        self.assertAllowed('python3 /repo/aiOS/tools/ideaVerse/research-capture.py check n.md')

    def test_inline_python_is_refused_because_it_reopens_everything(self):
        self.assertIn('may only launch', self.assertRefused('python3 -c "import os"'))

    def test_a_module_or_another_script_is_refused(self):
        self.assertRefused('python3 -m http.server')
        self.assertRefused('python3 scripts/whatever.py')

    def test_heredocs_are_refused_outright(self):
        self.assertIn('smuggle an interpreter', self.assertRefused("python3 <<'EOF'\nx\nEOF"))


class TestCurl(ScopeCase):
    """`curl` is a granted capability, not an inherited one.

    With no `agents.researcher.curlHosts` configured there is no probe target, and the
    head is refused outright — a framework that shipped a default host would be granting
    network reach no project asked for.
    """

    HOSTS = ('https://dev.example.test/', 'https://staging.example.test/')

    def setUp(self):
        patch = mock.patch.object(scope, 'CURL_HOSTS', self.HOSTS)
        patch.start()
        self.addCleanup(patch.stop)

    def test_reading_a_configured_host_is_allowed(self):
        self.assertAllowed('curl -s https://dev.example.test/api/v1/languages')

    def test_any_other_host_is_refused(self):
        self.assertIn('limited to', self.assertRefused('curl -s https://example.com/'))

    def test_write_verbs_are_refused_even_against_an_allowed_host(self):
        for flag in ('-X POST', '-d body', '--data body', '-T file', '--upload-file f',
                     '-F k=v', '--form k=v'):
            with self.subTest(flag=flag):
                reason = self.assertRefused(
                    f'curl {flag} https://staging.example.test/api')
                self.assertIn('read-only', reason)

    def test_with_no_host_configured_curl_is_refused_entirely(self):
        with mock.patch.object(scope, 'CURL_HOSTS', ()):
            reason = self.assertRefused('curl -s https://dev.example.test/api')
            self.assertIn('no `agents.researcher.curlHosts`', reason)


class TestWriteScope(unittest.TestCase):
    """Relative and absolute paths mean the same thing here — `refuse_write` resolves
    against the repo root, so a checkout under any directory name behaves identically."""

    def repo(self, relative: str) -> str:
        return str(REPO_ROOT / relative)

    def test_the_researchers_one_note_is_allowed(self):
        self.assertIsNone(scope.refuse_write(self.repo('docs/ideaVerse/atlas/concepts/x.md')))

    def test_a_scratchpad_path_is_allowed_for_answer_files_and_probe_output(self):
        self.assertIsNone(scope.refuse_write('/tmp/session/scratchpad/answer.md'))

    def test_the_generated_wiki_is_refused(self):
        self.assertIn('docs/wiki', scope.refuse_write(self.repo('docs/wiki/index.md')))

    def test_code_and_harness_paths_are_refused(self):
        self.assertIsNotNone(scope.refuse_write(self.repo('modules/core/lib/x.dart')))
        self.assertIsNotNone(scope.refuse_write(self.repo('.claude/skills/ideaverse-wiki-sync/SKILL.md')))

    def test_a_path_outside_the_repository_is_refused(self):
        self.assertIn('outside the repository', scope.refuse_write('/etc/hosts'))

    def test_an_empty_path_is_refused(self):
        self.assertEqual(scope.refuse_write(''), 'no file_path')

    def test_a_relative_path_means_the_same_thing_from_any_directory(self):
        # The harness invokes hooks from the project directory, but a relative path must
        # not mean different things by caller — it now resolves against the repo root.
        import os
        note = 'docs/ideaVerse/atlas/concepts/x.md'
        cwd = os.getcwd()
        try:
            os.chdir(REPO_ROOT)
            self.assertIsNone(scope.refuse_write(note))
            with tempfile.TemporaryDirectory() as elsewhere:
                os.chdir(elsewhere)
                self.assertIsNone(scope.refuse_write(note))
                self.assertIsNotNone(scope.refuse_write('lib/main.dart'))
        finally:
            os.chdir(cwd)


class TestProtectedPaths(unittest.TestCase):
    """Some vault notes are owned exclusively by another session.

    Which ones is a project's convention, not the framework's, so the hook reads
    `agents.researcher.protectedPaths` — a prefix list. The default is empty, which is
    why the refusal has to be configurable rather than guessed: a hook that protects
    the wrong directory reads as protection while guarding nothing.
    """

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        # .resolve(): on macOS tempfile hands back /var/... while resolve() yields
        # /private/var/..., and refuse_write compares a resolved path to REPO_ROOT.
        root = pathlib.Path(self._dir.name).resolve()
        self.vault = root / 'docs' / 'ideaVerse'
        self.works = self.vault / 'efforts' / 'works'
        self.works.mkdir(parents=True)
        self.addCleanup(self._dir.cleanup)
        for attr, value in (('REPO_ROOT', root),
                            ('PROTECTED', ('docs/ideaVerse/efforts/works/',))):
            patch = mock.patch.object(scope, attr, value)
            patch.start()
            self.addCleanup(patch.stop)

    def note(self, name: str) -> str:
        target = self.works / name
        target.write_text('---\ntags: []\n---\n\n# n\n')
        return str(target)

    def test_a_protected_path_is_refused(self):
        reason = scope.refuse_write(self.note('owned.md'))
        self.assertIsNotNone(reason)
        self.assertIn('protectedPaths', reason)

    def test_the_agent_s_own_note_elsewhere_in_the_vault_is_allowed(self):
        target = self.vault / 'calendar' / 'research'
        target.mkdir(parents=True)
        self.assertIsNone(scope.refuse_write(str(target / 'finding.md')))

    def test_nothing_is_protected_by_default(self):
        with mock.patch.object(scope, 'PROTECTED', ()):
            self.assertIsNone(scope.refuse_write(self.note('owned.md')))


class TestScratchpad(unittest.TestCase):
    """Outside the repo, a scratchpad is the only sanctioned target — matched as a path
    segment, so a checkout that lives under one keeps its full scope."""

    def test_a_scratchpad_outside_the_repo_is_allowed(self):
        self.assertIsNone(scope.refuse_write('/tmp/session/scratchpad/answer.md'))

    def test_a_repo_path_is_judged_on_its_own_terms_even_under_a_scratchpad_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root = (pathlib.Path(raw).resolve()) / 'scratchpad' / 'MobileCarrier'
            (root / 'lib').mkdir(parents=True)
            (root / 'docs' / 'ideaVerse').mkdir(parents=True)
            with mock.patch.object(scope, 'REPO_ROOT', root):
                self.assertIsNotNone(scope.refuse_write(str(root / 'lib' / 'main.dart')))
                self.assertIsNone(
                    scope.refuse_write(str(root / 'docs' / 'ideaVerse' / 'n.md')))

    def test_a_directory_merely_named_like_one_is_not_a_scratchpad(self):
        self.assertIsNotNone(scope.refuse_write('/tmp/scratchpadding/answer.md'))


class TestHookContract(unittest.TestCase):
    """Exit 0 is 'allowed, or not our business'; exit 2 is 'denied, tell the agent why'."""

    def _run(self, payload: str) -> tuple:
        buffer = io.StringIO()
        with mock.patch.object(scope.sys, 'stdin', io.StringIO(payload)), \
                redirect_stderr(buffer):
            return scope.main(), buffer.getvalue()

    def test_a_human_at_the_keyboard_is_never_constrained(self):
        # PreToolUse omits agent_type for the main session.
        code, _ = self._run('{"tool_name": "Bash", "tool_input": {"command": "git push"}}')
        self.assertEqual(code, 0)

    def test_another_agent_type_passes_through(self):
        code, _ = self._run('{"agent_type": "librarian", "tool_name": "Bash",'
                            ' "tool_input": {"command": "git push"}}')
        self.assertEqual(code, 0)

    def test_the_researcher_is_denied_with_the_reason_on_stderr(self):
        code, err = self._run('{"agent_type": "researcher", "tool_name": "Bash",'
                              ' "tool_input": {"command": "git push"}}')
        self.assertEqual(code, 2)
        self.assertIn('Refused by the Researcher scope', err)

    def test_an_allowed_command_is_not_denied(self):
        code, err = self._run('{"agent_type": "researcher", "tool_name": "Bash",'
                              ' "tool_input": {"command": "grep -rn x docs/"}}')
        self.assertEqual(code, 0)
        self.assertEqual(err, '')

    def test_every_edit_tool_is_scoped_not_just_write(self):
        for tool in ('Write', 'Edit', 'NotebookEdit'):
            with self.subTest(tool=tool):
                code, _ = self._run('{"agent_type": "researcher", "tool_name": "%s",'
                                    ' "tool_input": {"file_path": "lib/x.dart"}}' % tool)
                self.assertEqual(code, 2)

    def test_tools_it_does_not_police_pass_through(self):
        code, _ = self._run('{"agent_type": "researcher", "tool_name": "Read",'
                            ' "tool_input": {"file_path": "/etc/hosts"}}')
        self.assertEqual(code, 0)

    def test_malformed_input_fails_open_rather_than_blocking_the_turn(self):
        self.assertEqual(self._run('not json')[0], 0)


if __name__ == '__main__':
    unittest.main()
