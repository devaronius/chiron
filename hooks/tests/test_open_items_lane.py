"""The SessionStart hook that injects the ripe open-item digest.

It has one defining property: **it always exits 0**. A ledger problem must never block
a session from starting, and the worst acceptable outcome is a session with no digest —
which is exactly the behaviour that existed before the hook did.

That property is the only reason the hook is allowed to shell out to a scanner at all,
and until now nothing held it there. Every failure mode is covered here rather than
just the happy path, because the happy path is the one case that was never in doubt:
a missing scanner, a scanner that crashes, a scanner that hangs past TIMEOUT, and a
scanner that succeeds but says nothing.

Nothing here runs the real scanner or reads the real ledger — `subprocess.run` is
replaced — so these tests neither touch the vault nor depend on what happens to be due
on the day they run.
"""
from __future__ import annotations

import io
import pathlib
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _harness import lane, settings


def completed(stdout='', returncode=0):
    return subprocess.CompletedProcess(args=['python3'], returncode=returncode,
                                       stdout=stdout, stderr='')


class LaneHookCase(unittest.TestCase):
    """Runs main() with the scanner stubbed, returning (exit code, printed text)."""

    def run_hook(self, *, exists=True, result=None, raises=None):
        # A real Path in a temp dir rather than a mocked one: PosixPath.exists is
        # read-only, and a fake scanner path that is genuinely absent is the honest
        # version of the "missing scanner" case anyway.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        scanner = pathlib.Path(tmp.name) / 'open-items.py'
        if exists:
            scanner.write_text('')

        buf = io.StringIO()
        run = mock.patch.object(
            lane.subprocess, 'run',
            side_effect=raises if raises else None,
            return_value=result if result is not None else completed(),
        )
        with mock.patch.object(lane, 'SCANNER', scanner), run, redirect_stdout(buf):
            code = lane.main()
        return code, buf.getvalue()


class TestAlwaysExitsZero(LaneHookCase):
    """Each of these is a way the scanner can fail. None may stop a session."""

    def test_missing_scanner_is_silent(self):
        # A checkout without aiOS/ — a worktree mid-rebase, a partial clone.
        code, out = self.run_hook(exists=False)
        self.assertEqual(code, 0)
        self.assertEqual(out, '')

    def test_scanner_crash_is_silent(self):
        # A malformed ledger that makes the scanner raise: non-zero and no digest.
        code, out = self.run_hook(result=completed(returncode=1, stdout=''))
        self.assertEqual(code, 0)
        self.assertEqual(out, '')

    def test_scanner_timeout_is_silent(self):
        # TimeoutExpired is a SubprocessError, so the existing handler covers it —
        # pinned because that inheritance is the whole reason there is no second except.
        code, out = self.run_hook(
            raises=subprocess.TimeoutExpired(cmd='open-items.py', timeout=lane.TIMEOUT))
        self.assertEqual(code, 0)
        self.assertEqual(out, '')

    def test_unlaunchable_scanner_is_silent(self):
        # No interpreter, no permission, bad path: OSError rather than SubprocessError.
        code, out = self.run_hook(raises=OSError('cannot execute'))
        self.assertEqual(code, 0)
        self.assertEqual(out, '')

    def test_empty_digest_injects_nothing(self):
        # Nothing ripe and nothing parked. Success, but there is nothing to say, and a
        # heading with no items under it is noise at the top of every session.
        code, out = self.run_hook(result=completed(stdout='   \n'))
        self.assertEqual(code, 0)
        self.assertEqual(out, '')

    def test_nonzero_with_output_is_still_refused(self):
        # A scanner that printed a partial digest and then failed. Half a ledger is
        # worse than none: you would answer against items that may not be the ripe set.
        code, out = self.run_hook(result=completed(stdout='🧭 2 ripe', returncode=2))
        self.assertEqual(code, 0)
        self.assertEqual(out, '')


class TestDigestInjection(LaneHookCase):
    def test_digest_is_injected_under_a_heading_naming_what_is_owed(self):
        # The hook carries the data; the project's instruction file carries what a
        # disposition is. The heading is the link between them, so it is part of the
        # contract — and it names the three dispositions, because a digest nobody
        # knows how to answer becomes wallpaper.
        code, out = self.run_hook(result=completed(stdout='🧭 1 ripe\n  1. do a thing'))
        self.assertEqual(code, 0)
        self.assertIn('Open items owed a disposition', out)
        for disposition in ('start it', 'defer it', 'reassign it'):
            self.assertIn(disposition, out)
        self.assertIn('1. do a thing', out)

    def test_timeout_sits_inside_the_configured_hook_timeout(self):
        # If the inner timeout ever exceeds the outer one, the harness kills the hook
        # instead of the hook returning 0 — and the always-exit-0 guarantee is void.
        config = settings()
        if config is None:
            self.skipTest('no .claude/settings.json — the hook is not wired in this repo')
        timeouts = [
            h['timeout']
            for group in config.get('hooks', {}).get('SessionStart', [])
            for h in group.get('hooks', [])
            if 'open-items-lane.py' in h.get('command', '') and 'timeout' in h
        ]
        if not timeouts:
            self.skipTest('open-items-lane.py is not wired in this repo')
        self.assertLess(lane.TIMEOUT, min(timeouts))


if __name__ == '__main__':
    unittest.main()
