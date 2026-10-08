"""verify-claims: re-measure what a document claims.

The tool takes a **measurement name**, never a command. Two earlier designs let
note text name a program — first through a shell, then through an allowlist of
command heads — and both were escapable (`find -exec`, `git -c alias.x=!…`, a path
pattern admitting `../..`). The Stop hook runs this unattended over notes that
carry pasted clippings, so the only safe shape is one where note text cannot name
a program at all. These tests pin that boundary and the parsing around it.
"""
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'verify-claims.py'
_spec = importlib.util.spec_from_file_location('verify_claims', _PATH)
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)


def note(body: str) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / 'n.md'
    p.write_text(body, encoding='utf-8')
    return p


class TestNoteTextCannotNameAProgram(unittest.TestCase):
    """Every shape a previous design executed. None is a measurement name."""

    ESCAPES = [
        'find . -maxdepth 0 -exec touch /tmp/zz-vc ;',
        'git -c alias.b=!touch /tmp/zz-vc b',
        'sort -o /tmp/zz-vc README.md',
        'python3 aiOS/tools/../../docs/evil.py',
        'python3 aiOS/tools/ideaVerse/verify-claims.py --fix other.md',
        'echo 1; touch /tmp/zz-vc',
        'tail -1 /etc/hosts',
    ]

    def test_none_of_them_is_a_measurement(self):
        for call in self.ESCAPES:
            with self.subTest(call=call[:40]):
                ok, detail = vc.measure(call)
                self.assertFalse(ok)
                self.assertIn('is not a measurement', detail)

    def test_none_of_them_leaves_an_artifact(self):
        probe = pathlib.Path('/tmp/zz-vc')
        probe.unlink(missing_ok=True)
        for call in self.ESCAPES:
            vc.measure(call)
        self.assertFalse(probe.exists(), 'a refused call still ran')

    def test_a_path_argument_cannot_leave_the_repository(self):
        ok, detail = vc.measure('file-kb ../../../etc/hosts')
        self.assertFalse(ok)
        self.assertIn('outside the repository', detail)

    def test_a_measurement_rejects_the_wrong_arity(self):
        self.assertIn('no arguments', vc.measure('tests extra')[1])
        self.assertIn('exactly one argument', vc.measure('pdf-pages')[1])


class TestParsing(unittest.TestCase):
    def split(self, text: str):
        m = vc.CLAIM_RE.search(text)
        return vc.split_claim(m.group('body')) if m else None

    def test_a_claim_is_measurement_and_expectation(self):
        self.assertEqual(self.split('x <!--verify: tests = 7-->'), ('tests', '7'))

    def test_the_split_is_at_the_last_equals(self):
        self.assertEqual(self.split('<!--verify: file-kb a=b.md = 3-->'),
                         ('file-kb a=b.md', '3'))

    def test_a_marker_without_an_expectation_is_not_a_claim(self):
        self.assertIsNone(self.split('<!--verify: tests-->'))


class TestCodeIsNotAClaim(unittest.TestCase):
    """The note documenting this syntax shows a marker as inline code. Without this
    the tool measured its own documentation and failed the turn with no fix."""

    FORMS = {
        'backtick fence': '```\n<!--verify: tests = 1-->\n```\n',
        'tilde fence': '~~~\n<!--verify: tests = 1-->\n~~~\n',
        'indented block': '    <!--verify: tests = 1-->\n',
        'double span': 'write ``<!--verify: tests = 1-->`` here',
        'single span': 'write `<!--verify: tests = 1-->` here',
    }

    def test_no_code_form_is_treated_as_a_claim(self):
        for name, body in self.FORMS.items():
            with self.subTest(form=name):
                claims, _, _ = vc.check(note(body), fix=False)
                self.assertEqual(claims, 0)

    def test_a_real_marker_beside_code_is_still_found(self):
        # A stub, not `tests`: `check` measures, and measuring `tests` from inside
        # the suite runs the suite — 25s and a timeout, discovered the hard way.
        vc.MEASUREMENTS['zz-probe'] = (lambda _: '1', '', 'probe')
        try:
            claims, _, _ = vc.check(
                note('`inline` and <!--verify: zz-probe = 1--> here'), fix=False)
        finally:
            del vc.MEASUREMENTS['zz-probe']
        self.assertEqual(claims, 1)

    def test_blanking_preserves_offsets(self):
        """`--fix` indexes the original text with offsets from the blanked copy."""
        text = '`a` and ~~~\nx\n~~~\n and <!--verify: tests = 1-->'
        self.assertEqual(len(vc.strip_code(text)), len(text))


class TestMeasurements(unittest.TestCase):
    def test_every_registered_measurement_is_callable(self):
        for name, (func, arity, blurb) in vc.MEASUREMENTS.items():
            self.assertTrue(callable(func), name)
            self.assertTrue(blurb, f'{name} has no description')

    def test_counting_mermaid_fences_in_a_real_note(self):
        repo = pathlib.Path(__file__).resolve().parents[3]
        target = repo / 'docs/ideaVerse/calendar/research/research_note_failure_patterns.md'
        if not target.exists():
            self.skipTest('note not present')
            return
        ok, value = vc.measure(f'mermaid-diagrams {target.relative_to(repo)}')
        self.assertTrue(ok, value)
        self.assertTrue(value.isdigit())

    def test_a_measurement_that_returns_nothing_is_a_failure(self):
        """An empty result used to be written into the note by `--fix`, which left
        a marker that no longer parsed — a check that quietly stopped checking."""
        vc.MEASUREMENTS['zz-empty'] = (lambda _: '', '', 'probe')
        try:
            ok, detail = vc.measure('zz-empty')
        finally:
            del vc.MEASUREMENTS['zz-empty']
        self.assertFalse(ok)
        self.assertIn('measured nothing', detail)


class TestChecking(unittest.TestCase):
    def test_a_matching_claim_is_not_a_mismatch(self):
        vc.MEASUREMENTS['zz-seven'] = (lambda _: '7', '', 'probe')
        try:
            claims, stale, _ = vc.check(note('<!--verify: zz-seven = 7-->'), fix=False)
        finally:
            del vc.MEASUREMENTS['zz-seven']
        self.assertEqual((claims, stale), (1, 0))

    def test_fix_rewrites_the_expectation_in_place(self):
        vc.MEASUREMENTS['zz-nine'] = (lambda _: '9', '', 'probe')
        try:
            p = note('count <!--verify: zz-nine = 7--> here')
            _, stale, rewritten = vc.check(p, fix=True)
        finally:
            del vc.MEASUREMENTS['zz-nine']
        self.assertEqual(stale, 1)
        self.assertIn('zz-nine = 9', rewritten)
        self.assertIn('count ', rewritten)
        self.assertIn(' here', rewritten)


if __name__ == '__main__':
    unittest.main()
